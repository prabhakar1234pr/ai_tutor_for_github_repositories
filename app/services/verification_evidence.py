"""
Verification Evidence Collector Service
Orchestrates collection of all evidence types for task verification.
"""

import logging
from typing import Any

from app.core.supabase_client import get_supabase_client
from app.services.ast_analyzer import ASTAnalyzer
from app.services.docker_client import DockerClient, get_docker_client
from app.services.file_system import FileSystemService
from app.services.git_service import GitService
from app.services.github_evidence import GitHubEvidenceCollector
from app.services.pattern_matcher import PatternMatcher
from app.services.test_executor import TestExecutor
from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class VerificationEvidenceCollector:
    """
    Orchestrates collection of all evidence types for deep verification:
    - Git diff and status
    - User's code state (file contents)
    - Test execution results
    - AST analysis of user code
    - Pattern matching against extracted patterns
    - GitHub API evidence (notebook repo baseline)
    """

    def __init__(
        self,
        docker_client: DockerClient | None = None,
        github_token: str | None = None,
    ):
        self.docker = docker_client or get_docker_client()
        self.git_service = GitService(docker_client=self.docker)
        self.file_system = FileSystemService(docker_client=self.docker)
        self.test_executor = TestExecutor(docker_client=self.docker)
        self.ast_analyzer = ASTAnalyzer()
        self.pattern_matcher = PatternMatcher()
        self.github_collector = GitHubEvidenceCollector(github_token=github_token)
        self.workspace_manager = WorkspaceManager()
        self.supabase = get_supabase_client()

    async def collect_all_evidence(
        self,
        task_id: str,
        workspace_id: str,
        base_commit: str | None = None,
    ) -> dict[str, Any]:
        """
        Collect all evidence for task verification.

        Args:
            task_id: Task ID
            workspace_id: Workspace ID
            base_commit: Base commit hash (from task session)

        Returns:
            {
                "git_diff": str,
                "git_status": dict,
                "changed_files": [str],
                "file_contents": {file_path: content},
                "test_results": dict | None,
                "ast_analysis": dict,
                "pattern_match_results": dict | None,
                "github_evidence": dict | None,
                "workspace_id": str,
                "container_id": str
            }
        """
        logger.info(
            f"Collecting verification evidence for task {task_id}, workspace {workspace_id}"
        )

        # Get workspace and container
        workspace = self.workspace_manager.get_workspace(workspace_id)
        if not workspace or not workspace.container_id:
            raise ValueError(f"Workspace {workspace_id} not found or has no container")

        container_id = workspace.container_id

        # Get task info
        task_response = (
            self.supabase.table("tasks")
            .select("test_file_path, test_file_content, test_command, verification_patterns")
            .eq("task_id", task_id)
            .execute()
        )

        if not task_response.data:
            raise ValueError(f"Task {task_id} not found")

        task = task_response.data[0]
        test_file_path = task.get("test_file_path")
        test_command = task.get("test_command")
        verification_patterns = task.get("verification_patterns") or {}

        # 1. Git evidence
        git_diff_result = self.git_service.git_diff(
            container_id, base_commit=base_commit, head_commit="HEAD"
        )
        git_status_result = self.git_service.git_status(container_id)

        git_diff = git_diff_result.get("diff", "") if isinstance(git_diff_result, dict) else ""
        git_status = git_status_result if isinstance(git_status_result, dict) else {}

        # Extract changed files
        changed_files = []
        if isinstance(git_status, dict):
            changed_files.extend(git_status.get("modified", []))
            changed_files.extend(git_status.get("staged", []))
            changed_files.extend(git_status.get("untracked", []))

        # 2. File contents (limit to first 5 changed files, max 10KB each)
        file_contents = {}
        for file_path in changed_files[:5]:
            try:
                file_result = self.file_system.read_file(container_id, file_path)
                if file_result.get("success"):
                    content = file_result.get("content", "")
                    # Limit size
                    if len(content) <= 10000:
                        file_contents[file_path] = content
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")

        # 3. Test execution (if test file exists)
        test_results = None
        if test_command or test_file_path:
            test_results = self.test_executor.execute_test(
                container_id=container_id,
                test_file_path=test_file_path,
                test_command=test_command,
            )

        # 4. AST analysis of user code (from first changed file)
        ast_analysis = {}
        if file_contents:
            first_file_path = list(file_contents.keys())[0]
            first_file_content = file_contents[first_file_path]

            # Detect language from file extension
            language = "python"
            if first_file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
                language = "javascript"

            if language == "python":
                ast_analysis = self.ast_analyzer.analyze_python_code(first_file_content)
            else:
                ast_analysis = self.ast_analyzer.analyze_javascript_code(first_file_content)

        # 5. Pattern matching (if patterns exist)
        pattern_match_results = None
        if verification_patterns and file_contents:
            first_file_content = list(file_contents.values())[0]
            language = "python"
            if list(file_contents.keys())[0].endswith((".js", ".jsx", ".ts", ".tsx")):
                language = "javascript"

            pattern_match_results = self.pattern_matcher.match_patterns(
                user_code=first_file_content,
                patterns=verification_patterns,
                language=language,
            )

        # 6. GitHub evidence (notebook repo baseline) - optional, async
        github_evidence = None
        try:
            # Get project to find user_repo_url
            project_response = (
                self.supabase.table("projects")
                .select("user_repo_url, github_access_token")
                .eq("project_id", workspace.project_id)
                .execute()
            )

            if project_response.data:
                project = project_response.data[0]
                user_repo_url = project.get("user_repo_url")

                if user_repo_url:
                    github_evidence = await self.github_collector.get_repo_baseline(
                        user_repo_url, file_paths=changed_files[:5]
                    )
        except Exception as e:
            logger.warning(f"Failed to collect GitHub evidence: {e}")

        return {
            "git_diff": git_diff,
            "git_status": git_status,
            "changed_files": changed_files,
            "file_contents": file_contents,
            "test_results": test_results,
            "ast_analysis": ast_analysis,
            "pattern_match_results": pattern_match_results,
            "github_evidence": github_evidence,
            "workspace_id": workspace_id,
            "container_id": container_id,
        }
