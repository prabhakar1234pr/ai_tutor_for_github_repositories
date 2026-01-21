"""
Verification Pipeline Service
Orchestrates multi-layered task verification with proper error handling.

Pipeline Steps:
1. Detect project language
2. Filter relevant files (exclude node_modules, .git, etc.)
3. Ensure test framework is installed
4. Run tests (with graceful failure)
5. Collect evidence (git diff, AST, file contents)
6. HTTP testing for web tasks (optional)
7. LLM verification
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.supabase_client import get_supabase_client
from app.services.ast_analyzer import ASTAnalyzer
from app.services.docker_client import DockerClient, get_docker_client
from app.services.file_system import FileSystemService
from app.services.git_service import GitService
from app.services.pattern_matcher import PatternMatcher
from app.services.workspace_manager import get_workspace_manager

logger = logging.getLogger(__name__)


class ProjectLanguage(Enum):
    """Detected project language."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"


@dataclass
class VerificationState:
    """State object tracking verification progress."""

    task_id: str
    workspace_id: str
    container_id: str | None = None

    # Detection results
    language: ProjectLanguage = ProjectLanguage.UNKNOWN
    has_package_json: bool = False
    has_requirements_txt: bool = False
    has_pyproject_toml: bool = False

    # File filtering
    all_files: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    file_contents: dict[str, str] = field(default_factory=dict)

    # Git evidence
    git_diff: str = ""
    git_status: dict = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)

    # Test results
    test_framework_installed: bool = False
    test_results: dict | None = None
    test_output: str = ""
    test_passed: bool | None = None

    # AST analysis
    ast_analysis: dict = field(default_factory=dict)

    # Pattern matching
    pattern_match_results: dict | None = None

    # HTTP testing (for web tasks)
    http_test_results: dict | None = None

    # Errors (non-fatal)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Final result
    verification_passed: bool | None = None
    llm_analysis: dict = field(default_factory=dict)


# Files/directories to always exclude
EXCLUDE_PATTERNS = [
    "node_modules/",
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    ".venv/",
    "venv/",
    ".env",
    "*.pyc",
    "*.pyo",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "*.log",
    "*.min.js",
    "*.min.css",
    "dist/",
    "build/",
    ".next/",
    "coverage/",
]


class VerificationPipeline:
    """
    Multi-layered verification pipeline with graceful error handling.

    Each step can fail independently without breaking the entire pipeline.
    Results are accumulated in VerificationState.
    """

    def __init__(self, docker_client: DockerClient | None = None):
        self.docker = docker_client or get_docker_client()
        self.git_service = GitService(docker_client=self.docker)
        self.file_system = FileSystemService(docker_client=self.docker)
        self.ast_analyzer = ASTAnalyzer()
        self.pattern_matcher = PatternMatcher()
        self.workspace_manager = get_workspace_manager()
        self.supabase = get_supabase_client()

    async def run_verification(
        self,
        task_id: str,
        workspace_id: str,
        base_commit: str | None = None,
    ) -> VerificationState:
        """
        Run the full verification pipeline.

        Args:
            task_id: Task to verify
            workspace_id: Workspace containing user's code
            base_commit: Base commit for diff (optional)

        Returns:
            VerificationState with all collected evidence and results
        """
        state = VerificationState(task_id=task_id, workspace_id=workspace_id)

        logger.info(f"🚀 Starting verification pipeline for task {task_id}")

        # Step 0: Get workspace and container
        state = self._step_get_workspace(state)
        if not state.container_id:
            state.errors.append("Failed to get container - cannot proceed")
            return state

        # Step 1: Detect project language
        state = self._step_detect_language(state)
        logger.info(f"📋 Detected language: {state.language.value}")

        # Step 2: Collect git evidence
        state = self._step_collect_git_evidence(state, base_commit)
        logger.info(f"📊 Git: {len(state.changed_files)} changed files")

        # Step 3: Filter and read relevant files
        state = self._step_filter_and_read_files(state)
        logger.info(f"📁 Reading {len(state.relevant_files)} relevant files")

        # Step 4: Ensure test framework is installed
        state = await self._step_ensure_test_framework(state)

        # Step 5: Run tests
        state = await self._step_run_tests(state, task_id)
        if state.test_passed is not None:
            logger.info(f"🧪 Tests: {'PASSED' if state.test_passed else 'FAILED'}")
        else:
            logger.info("🧪 Tests: Not run (no test file or command)")

        # Step 6: AST analysis
        state = self._step_ast_analysis(state)

        # Step 7: Pattern matching
        state = await self._step_pattern_matching(state, task_id)

        # Step 8: HTTP testing for web tasks
        state = await self._step_http_testing(state, task_id)

        logger.info(
            f"✅ Pipeline complete. Warnings: {len(state.warnings)}, Errors: {len(state.errors)}"
        )

        return state

    def _step_get_workspace(self, state: VerificationState) -> VerificationState:
        """Get workspace and container ID."""
        try:
            workspace = self.workspace_manager.get_workspace(state.workspace_id)
            if workspace and workspace.container_id:
                state.container_id = workspace.container_id
            else:
                state.errors.append("Workspace not found or has no container")
        except Exception as e:
            state.errors.append(f"Failed to get workspace: {e}")
        return state

    def _step_detect_language(self, state: VerificationState) -> VerificationState:
        """Detect project language from files."""
        if not state.container_id:
            return state

        try:
            # Check for package.json (JavaScript/TypeScript)
            pkg_content = self.file_system.read_file(state.container_id, "package.json")
            if pkg_content:
                state.has_package_json = True
                # Check if TypeScript
                if '"typescript"' in pkg_content or "tsconfig.json" in pkg_content:
                    state.language = ProjectLanguage.TYPESCRIPT
                else:
                    state.language = ProjectLanguage.JAVASCRIPT
                return state
        except Exception:
            pass

        try:
            # Check for requirements.txt (Python)
            req_content = self.file_system.read_file(state.container_id, "requirements.txt")
            if req_content:
                state.has_requirements_txt = True
                state.language = ProjectLanguage.PYTHON
                return state
        except Exception:
            pass

        try:
            # Check for pyproject.toml (Python)
            pyproject = self.file_system.read_file(state.container_id, "pyproject.toml")
            if pyproject:
                state.has_pyproject_toml = True
                state.language = ProjectLanguage.PYTHON
                return state
        except Exception:
            pass

        # Fallback: check file extensions in workspace
        try:
            files = self.file_system.list_files(state.container_id, "/workspace")
            if files:
                file_names = [f.get("name", "") for f in files]
                py_count = sum(1 for f in file_names if f.endswith(".py"))
                js_count = sum(1 for f in file_names if f.endswith((".js", ".jsx", ".ts", ".tsx")))

                if py_count > js_count:
                    state.language = ProjectLanguage.PYTHON
                elif js_count > 0:
                    state.language = ProjectLanguage.JAVASCRIPT
        except Exception as e:
            state.warnings.append(f"Failed to detect language from files: {e}")

        return state

    def _step_collect_git_evidence(
        self, state: VerificationState, base_commit: str | None
    ) -> VerificationState:
        """Collect git diff and status."""
        if not state.container_id:
            return state

        try:
            # Get git diff
            diff_result = self.git_service.git_diff(
                state.container_id, base_commit=base_commit, head_commit="HEAD"
            )
            if isinstance(diff_result, dict):
                state.git_diff = diff_result.get("diff", "")
        except Exception as e:
            state.warnings.append(f"Failed to get git diff: {e}")

        try:
            # Get git status
            status_result = self.git_service.git_status(state.container_id)
            if isinstance(status_result, dict):
                state.git_status = status_result
                # Extract changed files
                state.changed_files = []
                state.changed_files.extend(status_result.get("modified", []))
                state.changed_files.extend(status_result.get("staged", []))
                state.changed_files.extend(status_result.get("untracked", []))
        except Exception as e:
            state.warnings.append(f"Failed to get git status: {e}")

        # Also extract files from git diff
        if state.git_diff:
            diff_files = re.findall(r"^diff --git a/(.+?) b/", state.git_diff, re.MULTILINE)
            for f in diff_files:
                if f not in state.changed_files:
                    state.changed_files.append(f)

        return state

    def _step_filter_and_read_files(self, state: VerificationState) -> VerificationState:
        """Filter out irrelevant files and read contents."""
        if not state.container_id:
            return state

        # Filter changed files
        state.relevant_files = []
        for file_path in state.changed_files:
            if self._should_include_file(file_path):
                state.relevant_files.append(file_path)

        # Limit to first 10 relevant files
        files_to_read = state.relevant_files[:10]

        # Always try to include key files
        key_files = [
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "server.js",
            "app.py",
            "main.py",
        ]
        for key_file in key_files:
            if key_file not in files_to_read:
                try:
                    content = self.file_system.read_file(state.container_id, key_file)
                    if content:
                        files_to_read.append(key_file)
                except Exception:
                    pass

        # Read file contents
        for file_path in files_to_read:
            try:
                content = self.file_system.read_file(state.container_id, file_path)
                if content:
                    # Limit size per file
                    if len(content) > 15000:
                        content = content[:15000] + "\n... (truncated)"
                    state.file_contents[file_path] = content
            except Exception as e:
                state.warnings.append(f"Failed to read {file_path}: {e}")

        return state

    def _should_include_file(self, file_path: str) -> bool:
        """Check if file should be included in verification."""
        for pattern in EXCLUDE_PATTERNS:
            if pattern.endswith("/"):
                # Directory pattern
                if file_path.startswith(pattern) or f"/{pattern}" in file_path:
                    return False
            elif pattern.startswith("*"):
                # Extension pattern
                if file_path.endswith(pattern[1:]):
                    return False
            else:
                # Exact match
                if file_path == pattern or file_path.endswith(f"/{pattern}"):
                    return False
        return True

    async def _step_ensure_test_framework(self, state: VerificationState) -> VerificationState:
        """Ensure appropriate test framework is installed."""
        if not state.container_id:
            return state

        try:
            if state.language == ProjectLanguage.PYTHON:
                # Check if pytest is installed
                exit_code, output = self.docker.exec_command(
                    state.container_id, "python -c 'import pytest'"
                )
                if exit_code != 0:
                    logger.info("📦 Installing pytest...")
                    exit_code, output = self.docker.exec_command(
                        state.container_id, "pip install pytest -q"
                    )
                    if exit_code == 0:
                        state.test_framework_installed = True
                        logger.info("✅ pytest installed")
                    else:
                        state.warnings.append(f"Failed to install pytest: {output}")
                else:
                    state.test_framework_installed = True

            elif state.language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
                # Check if jest or mocha is available
                exit_code, _ = self.docker.exec_command(state.container_id, "npx jest --version")
                if exit_code != 0:
                    # Try to install jest
                    logger.info("📦 Installing jest...")
                    exit_code, output = self.docker.exec_command(
                        state.container_id,
                        "npm install --save-dev jest 2>/dev/null || true",
                    )
                    # Check again
                    exit_code2, _ = self.docker.exec_command(
                        state.container_id, "npx jest --version"
                    )
                    if exit_code2 == 0:
                        state.test_framework_installed = True
                        logger.info("✅ jest installed")
                    else:
                        state.warnings.append("Jest not available - tests may fail")
                else:
                    state.test_framework_installed = True
        except Exception as e:
            state.warnings.append(f"Failed to ensure test framework: {e}")

        return state

    async def _step_run_tests(self, state: VerificationState, task_id: str) -> VerificationState:
        """Run tests for the task."""
        if not state.container_id:
            return state

        try:
            # Get task test info from database
            task_response = (
                self.supabase.table("tasks")
                .select("test_file_path, test_command, test_file_content")
                .eq("task_id", task_id)
                .execute()
            )

            if not task_response.data:
                state.warnings.append("Task not found in database")
                return state

            task = task_response.data[0]
            test_command = task.get("test_command")
            test_file_path = task.get("test_file_path")
            test_file_content = task.get("test_file_content")

            if not test_command and not test_file_path:
                state.warnings.append("No test command or file specified for task")
                return state

            # Write test file if content provided
            if test_file_content and test_file_path:
                try:
                    # Create directory if needed
                    test_dir = "/".join(test_file_path.split("/")[:-1])
                    if test_dir:
                        self.docker.exec_command(
                            state.container_id, f"mkdir -p /workspace/{test_dir}"
                        )

                    # Write test file
                    self.file_system.write_file(
                        state.container_id, test_file_path, test_file_content
                    )
                    logger.info(f"📝 Created test file: {test_file_path}")
                except Exception as e:
                    state.warnings.append(f"Failed to create test file: {e}")

            # Build test command based on language if not specified
            if not test_command:
                if test_file_path:
                    if state.language == ProjectLanguage.PYTHON:
                        test_command = f"pytest {test_file_path} -v"
                    elif state.language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
                        test_command = f"npx jest {test_file_path} --passWithNoTests"
                    else:
                        test_command = f"pytest {test_file_path} -v"  # Default

            # Fix command if language mismatch detected
            if test_command:
                test_command = self._fix_test_command(test_command, state.language)

            if test_command:
                logger.info(f"🧪 Running: {test_command}")
                exit_code, output = self.docker.exec_command(
                    state.container_id, test_command, workdir="/workspace"
                )

                state.test_output = output
                state.test_passed = exit_code == 0
                state.test_results = {
                    "success": True,
                    "exit_code": exit_code,
                    "output": output,
                    "passed": state.test_passed,
                    "command": test_command,
                }

        except Exception as e:
            state.warnings.append(f"Test execution error: {e}")
            state.test_results = {
                "success": False,
                "error": str(e),
                "passed": False,
            }

        return state

    def _fix_test_command(self, command: str, language: ProjectLanguage) -> str:
        """Fix test command if it doesn't match detected language."""
        # If Python project but command uses pytest and it's not installed, keep it
        # If JS project but command uses pytest, switch to jest
        if language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
            if "pytest" in command:
                # Extract the test file path
                match = re.search(r"pytest\s+(\S+)", command)
                if match:
                    test_path = match.group(1)
                    # Convert .py to .test.js
                    js_test_path = test_path.replace(".py", ".test.js")
                    return f"npx jest {js_test_path} --passWithNoTests"
                return "npm test"

        return command

    def _step_ast_analysis(self, state: VerificationState) -> VerificationState:
        """Perform AST analysis on all relevant files."""
        combined_analysis = {
            "functions": [],
            "classes": [],
            "imports": [],
            "has_syntax_errors": False,
            "files_analyzed": [],
        }

        for file_path, content in state.file_contents.items():
            try:
                # Determine language from file extension
                if file_path.endswith(".py"):
                    analysis = self.ast_analyzer.analyze_python_code(content)
                elif file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
                    analysis = self.ast_analyzer.analyze_javascript_code(content)
                else:
                    continue

                # Merge results
                combined_analysis["files_analyzed"].append(file_path)
                combined_analysis["functions"].extend(analysis.get("functions", []))
                combined_analysis["classes"].extend(analysis.get("classes", []))
                combined_analysis["imports"].extend(analysis.get("imports", []))

                if analysis.get("has_syntax_errors"):
                    combined_analysis["has_syntax_errors"] = True
                    combined_analysis["syntax_error"] = analysis.get("syntax_error")

            except Exception as e:
                state.warnings.append(f"AST analysis failed for {file_path}: {e}")

        state.ast_analysis = combined_analysis
        return state

    async def _step_pattern_matching(
        self, state: VerificationState, task_id: str
    ) -> VerificationState:
        """Match code against verification patterns."""
        try:
            # Get patterns from task
            task_response = (
                self.supabase.table("tasks")
                .select("verification_patterns")
                .eq("task_id", task_id)
                .execute()
            )

            if task_response.data:
                patterns = task_response.data[0].get("verification_patterns")
                if patterns and state.file_contents:
                    # Combine all file contents for pattern matching
                    all_code = "\n\n".join(state.file_contents.values())
                    language = (
                        "python" if state.language == ProjectLanguage.PYTHON else "javascript"
                    )

                    state.pattern_match_results = self.pattern_matcher.match_patterns(
                        user_code=all_code,
                        patterns=patterns,
                        language=language,
                    )
        except Exception as e:
            state.warnings.append(f"Pattern matching failed: {e}")

        return state

    async def _step_http_testing(self, state: VerificationState, task_id: str) -> VerificationState:
        """Run HTTP tests for web tasks."""
        if not state.container_id:
            return state

        try:
            # Get task description to check if it's a web task
            task_response = (
                self.supabase.table("tasks")
                .select("description, title")
                .eq("task_id", task_id)
                .execute()
            )

            if not task_response.data:
                return state

            task = task_response.data[0]
            description = (task.get("description") or "").lower()
            title = (task.get("title") or "").lower()

            # Check if this is a web task
            web_keywords = [
                "route",
                "endpoint",
                "api",
                "server",
                "express",
                "flask",
                "http",
                "get request",
                "post request",
            ]
            is_web_task = any(kw in description or kw in title for kw in web_keywords)

            if not is_web_task:
                return state

            logger.info("🌐 Detected web task - running HTTP tests")

            # Try to detect running server port
            ports_to_try = [3000, 5000, 8080, 8000, 4000]

            http_results = {
                "is_web_task": True,
                "server_detected": False,
                "endpoints_tested": [],
            }

            for port in ports_to_try:
                try:
                    # Try to curl the server from inside the container
                    exit_code, output = self.docker.exec_command(
                        state.container_id,
                        f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/ 2>/dev/null || echo 'failed'",
                        workdir="/workspace",
                    )

                    if exit_code == 0 and output.strip() not in ["failed", "000", ""]:
                        http_results["server_detected"] = True
                        http_results["port"] = port

                        # Try to get the actual response
                        exit_code2, response = self.docker.exec_command(
                            state.container_id,
                            f"curl -s http://localhost:{port}/",
                            workdir="/workspace",
                        )

                        http_results["endpoints_tested"].append(
                            {
                                "url": f"http://localhost:{port}/",
                                "status_code": output.strip(),
                                "response": response[:1000] if response else "",
                            }
                        )

                        logger.info(
                            f"✅ Server detected on port {port}, response: {output.strip()}"
                        )
                        break

                except Exception:
                    continue

            if not http_results["server_detected"]:
                http_results["message"] = (
                    "No server detected. Student may need to start the server."
                )
                state.warnings.append("Web task detected but no server running")

            state.http_test_results = http_results

        except Exception as e:
            state.warnings.append(f"HTTP testing failed: {e}")

        return state

    def get_evidence_for_llm(self, state: VerificationState) -> dict[str, Any]:
        """Convert state to evidence dict for LLM verifier."""
        return {
            "language": state.language.value,
            "git_diff": state.git_diff,
            "git_status": state.git_status,
            "changed_files": state.changed_files,
            "file_contents": state.file_contents,
            "test_results": state.test_results,
            "ast_analysis": state.ast_analysis,
            "pattern_match_results": state.pattern_match_results,
            "http_test_results": state.http_test_results,
            "warnings": state.warnings,
            "errors": state.errors,
            "workspace_id": state.workspace_id,
            "container_id": state.container_id,
        }


# Singleton instance
_verification_pipeline: VerificationPipeline | None = None


def get_verification_pipeline() -> VerificationPipeline:
    """Get or create the VerificationPipeline singleton."""
    global _verification_pipeline
    if _verification_pipeline is None:
        _verification_pipeline = VerificationPipeline()
    return _verification_pipeline
