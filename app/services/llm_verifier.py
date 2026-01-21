"""
LLM Verifier Service
Makes final verification decision using LLM based on all collected evidence.
"""

import logging
from typing import Any

from app.services.groq_service import get_groq_service
from app.utils.json_parser import parse_llm_json_response_async

logger = logging.getLogger(__name__)

# Enhanced verification prompt with multi-layered evidence
VERIFICATION_PROMPT = """You are a STRICT code reviewer. Verify if the student's code fulfills ALL task requirements.

**TASK DESCRIPTION:**
{task_description}

**EVIDENCE COLLECTED:**

1. PROJECT LANGUAGE: {language}

2. FILES CHANGED:
{changed_files}

3. CODE CONTENTS:
{file_contents}

4. GIT DIFF (what changed):
{git_diff}

5. TEST RESULTS:
{test_results}

6. AST ANALYSIS (code structure):
{ast_analysis}

7. HTTP TEST RESULTS (for web tasks):
{http_test_results}

8. PATTERN MATCHING:
{pattern_match_results}

**VERIFICATION RULES (STRICT):**
1. If tests FAILED → task MUST fail (unless test framework itself had issues)
2. If syntax errors detected → task MUST fail
3. If required functions/routes/endpoints are missing → task MUST fail
4. For web tasks: If HTTP test shows server not responding correctly → verify code structure at minimum
5. Check package.json/requirements.txt for required dependencies
6. Only PASS if ALL requirements are clearly met

**VERIFICATION CHECKLIST:**
- Does the code implement exactly what was asked?
- Are all specific requirements from the description met?
- Does the code produce the expected output/behavior?
- Are there any critical bugs or issues?

**CRITICAL DISTINCTION - READ CAREFULLY:**

"issues_found" vs "suggestions" are DIFFERENT:

- **"issues_found"**: ONLY actual problems that prevent code from working correctly
  - Bugs, syntax errors, missing functionality, incorrect implementation
  - If task PASSED and code works correctly, use empty array []
  - Do NOT include code quality improvements here

- **"suggestions"**: Optional enhancements and best practices
  - Error handling improvements, code organization, best practices
  - These are NOT issues - they are optional improvements
  - Code can work perfectly fine without these suggestions

**IMPORTANT**: Do NOT flag working code as having "issues" just because it could be improved. If the code works and meets requirements, "issues_found" should be empty [].

**Return ONLY valid JSON (no markdown, no extra text):**
{{
  "passed": true/false,
  "overall_feedback": "2-3 sentence summary explaining decision",
  "requirements_check": {{
    "code_implements_task": {{"met": true/false, "feedback": "..."}},
    "meets_all_requirements": {{"met": true/false, "feedback": "..."}},
    "no_critical_issues": {{"met": true/false, "feedback": "..."}}
  }},
  "hints": ["Helpful hint if failed"],
  "issues_found": ["ONLY actual problems: bugs, missing functionality, syntax errors. If task PASSED and code works, use empty array []."],
  "suggestions": ["Optional code quality improvements, best practices, enhancements. These are NOT issues - they are optional improvements."],
  "code_quality": "good/acceptable/needs_improvement",
  "test_status": "passed/failed/not_run/error",
  "pattern_match_status": "all_matched/partial/none"
}}
"""


class LLMVerifier:
    """
    Makes final verification decision using LLM based on all collected evidence.
    Uses strict verification philosophy - assumes wrong unless proven correct.
    """

    def __init__(self):
        self.groq_service = get_groq_service()

    async def verify_with_evidence(
        self,
        task_description: str,
        task_requirements: str,
        evidence: dict[str, Any],
        temperature: float = 0.0,  # Strict mode - deterministic
    ) -> dict[str, Any]:
        """
        Verify task using all collected evidence.

        Args:
            task_description: Task description
            task_requirements: Task requirements (can be same as description)
            evidence: Evidence dict from VerificationPipeline
            temperature: LLM temperature (0.0 for strict, deterministic)

        Returns:
            {
                "passed": bool,
                "overall_feedback": str,
                "requirements_check": dict,
                "hints": list[str],
                "issues_found": list[str],
                "suggestions": list[str],
                "code_quality": str,
                "test_status": str,
                "pattern_match_status": str
            }
        """
        logger.info("Running LLM verification with collected evidence")

        # Get language
        language = evidence.get("language", "unknown")

        # Format evidence for prompt with reasonable size limits
        git_diff = evidence.get("git_diff", "No git diff available")
        changed_files_list = evidence.get("changed_files", [])[:15]
        changed_files = "\n".join(f"- {f}" for f in changed_files_list) or "No files changed"

        file_contents_str = self._format_file_contents(evidence.get("file_contents", {}))
        test_results_str = self._format_test_results(evidence.get("test_results"))
        ast_analysis_str = self._format_ast_analysis(evidence.get("ast_analysis", {}))
        pattern_match_str = self._format_pattern_match(evidence.get("pattern_match_results"))
        http_test_str = self._format_http_test_results(evidence.get("http_test_results"))

        # Include warnings/errors from pipeline
        warnings = evidence.get("warnings", [])
        if warnings:
            logger.info(f"Pipeline warnings: {warnings}")

        # Build prompt with balanced size limits
        prompt = VERIFICATION_PROMPT.format(
            task_description=task_description[:500],  # More room for description
            language=language,
            git_diff=self._smart_truncate(git_diff, 1500),  # Keep important parts
            changed_files=changed_files[:400],
            file_contents=self._smart_truncate(file_contents_str, 3000),  # More room for code
            test_results=test_results_str[:500] if test_results_str else "No tests run",
            ast_analysis=ast_analysis_str[:400],
            http_test_results=(
                http_test_str[:400] if http_test_str else "Not a web task or server not running"
            ),
            pattern_match_results=(
                pattern_match_str[:300] if pattern_match_str else "No patterns to match"
            ),
        )

        # Log prompt size for debugging
        prompt_size = len(prompt)
        logger.info(f"Prompt size: {prompt_size} chars")

        # Emergency truncation only if really needed
        if prompt_size > 12000:
            logger.warning(f"Prompt size ({prompt_size}) exceeds limit, truncating...")
            prompt = prompt[:12000] + "\n\n... (truncated due to size limit)"

        system_prompt = (
            "You are a STRICT but fair code reviewer. "
            "Verify code against requirements. "
            "Return ONLY valid JSON object, no markdown code blocks, no extra text."
        )

        try:
            # Call LLM with strict temperature
            response = await self.groq_service.generate_response_async(
                user_query=prompt,
                system_prompt=system_prompt,
                context="",
                temperature=temperature,
            )

            # Parse JSON response
            verification_result = await parse_llm_json_response_async(
                response, expected_type="object"
            )

            logger.info(
                f"Verification complete: {'PASSED' if verification_result.get('passed') else 'FAILED'}"
            )

            return verification_result

        except Exception as e:
            logger.error(f"LLM verification error: {e}", exc_info=True)
            # Return safe failure result
            return {
                "passed": False,
                "overall_feedback": f"Verification error: {str(e)}",
                "requirements_check": {},
                "hints": ["Please check your code and try again."],
                "issues_found": [f"Verification system error: {str(e)}"],
                "suggestions": [],
                "code_quality": "needs_improvement",
                "test_status": "error",
                "pattern_match_status": "error",
            }

    def _format_file_contents(self, file_contents: dict[str, str]) -> str:
        """Format file contents for prompt."""
        if not file_contents:
            return "No file contents available"

        parts = []
        for file_path, content in file_contents.items():
            parts.append(f"=== {file_path} ===\n{content}\n")
        return "\n".join(parts)

    def _format_test_results(self, test_results: dict[str, Any] | None) -> str:
        """Format test results for prompt."""
        if not test_results:
            return "No test results available"

        if not test_results.get("success"):
            return f"Test execution failed: {test_results.get('error', 'Unknown error')}"

        passed = test_results.get("passed", False)
        exit_code = test_results.get("exit_code", -1)
        output = test_results.get("output", "")

        status = "PASSED" if passed else "FAILED"
        return f"Test Status: {status}\nExit Code: {exit_code}\nOutput:\n{output}"

    def _format_ast_analysis(self, ast_analysis: dict[str, Any]) -> str:
        """Format AST analysis for prompt."""
        if not ast_analysis:
            return "No AST analysis available"

        if ast_analysis.get("has_syntax_errors"):
            return f"Syntax Error: {ast_analysis.get('syntax_error', 'Unknown')}"

        functions = ast_analysis.get("functions", [])
        classes = ast_analysis.get("classes", [])
        imports = ast_analysis.get("imports", [])

        parts = []
        if functions:
            func_names = [f["name"] for f in functions]
            parts.append(f"Functions found: {', '.join(func_names)}")
        if classes:
            class_names = [c["name"] for c in classes]
            parts.append(f"Classes found: {', '.join(class_names)}")
        if imports:
            import_modules = [imp.get("module", "") for imp in imports]
            parts.append(f"Imports found: {', '.join(import_modules)}")

        return "\n".join(parts) if parts else "No functions, classes, or imports detected"

    def _format_pattern_match(self, pattern_match: dict[str, Any] | None) -> str:
        """Format pattern match results for prompt."""
        if not pattern_match:
            return "No pattern matching performed"

        all_matched = pattern_match.get("all_required_matched", False)
        required_functions = pattern_match.get("required_functions", {})
        required_classes = pattern_match.get("required_classes", {})

        parts = []
        parts.append(f"All required patterns matched: {all_matched}")

        if required_functions:
            func_status = []
            for func_name, status in required_functions.items():
                matched = status.get("matched", False)
                func_status.append(f"{func_name}: {'✓' if matched else '✗'}")
            parts.append(f"Required functions: {', '.join(func_status)}")

        if required_classes:
            class_status = []
            for class_name, status in required_classes.items():
                matched = status.get("matched", False)
                class_status.append(f"{class_name}: {'✓' if matched else '✗'}")
            parts.append(f"Required classes: {', '.join(class_status)}")

        return "\n".join(parts)

    def _format_github_evidence(self, github_evidence: dict[str, Any] | None) -> str:
        """Format GitHub evidence for prompt - keep minimal to avoid payload issues."""
        if not github_evidence:
            return "No GitHub baseline available"

        repo_structure = github_evidence.get("repo_structure", [])
        files = github_evidence.get("files", {})

        parts = []
        if repo_structure:
            parts.append(f"Repository structure: {len(repo_structure)} items")
        if files:
            # Only list file names, not contents, and limit to 5 files
            file_names = list(files.keys())[:5]
            parts.append(f"Baseline files available: {', '.join(file_names)}")
            if len(files) > 5:
                parts.append(f"... and {len(files) - 5} more files")

        return "\n".join(parts) if parts else "GitHub baseline available but empty"

    def _format_http_test_results(self, http_results: dict[str, Any] | None) -> str:
        """Format HTTP test results for prompt."""
        if not http_results:
            return "No HTTP testing performed"

        if not http_results.get("is_web_task"):
            return "Not a web task"

        parts = []

        if http_results.get("server_detected"):
            port = http_results.get("port", "unknown")
            parts.append(f"✓ Server detected on port {port}")

            endpoints = http_results.get("endpoints_tested", [])
            for endpoint in endpoints:
                url = endpoint.get("url", "")
                status = endpoint.get("status_code", "")
                response = endpoint.get("response", "")[:200]
                parts.append(f"  - {url}: Status {status}")
                if response:
                    parts.append(f"    Response: {response}")
        else:
            parts.append("✗ No server detected running")
            parts.append(
                "  Student may need to start the server with 'node server.js' or 'npm start'"
            )
            if http_results.get("message"):
                parts.append(f"  Note: {http_results['message']}")

        return "\n".join(parts)

    def _smart_truncate(self, text: str, max_length: int) -> str:
        """
        Smart truncation that tries to preserve important parts.
        Keeps beginning and end, truncates middle.
        """
        if len(text) <= max_length:
            return text

        # For very short limits, just truncate from end
        if max_length < 500:
            return text[:max_length] + "..."

        # Keep 60% from beginning, 30% from end
        begin_len = int(max_length * 0.6)
        end_len = int(max_length * 0.3)

        begin_part = text[:begin_len]
        end_part = text[-end_len:]

        return f"{begin_part}\n\n... (middle truncated) ...\n\n{end_part}"
