"""
LLM Verifier Service
Makes final verification decision using LLM based on all collected evidence.
"""

import logging
from typing import Any

from app.services.groq_service import get_groq_service
from app.utils.json_parser import parse_llm_json_response_async

logger = logging.getLogger(__name__)

# Enhanced verification prompt that uses all evidence types
VERIFICATION_PROMPT = """You are a STRICT code reviewer verifying if a student's code fulfills task requirements.

**VERIFICATION PHILOSOPHY:**
- Assume code is WRONG unless proven correct
- Be CRITICAL - find problems, don't overlook them
- NO partial credit - either it works or it doesn't
- Code must be COMPLETE, CORRECT, and FUNCTIONAL

**Task Description:**
{task_description}

**Task Requirements:**
{task_requirements}

**Evidence Collected:**

1. **Git Changes:**
{git_diff}

2. **Changed Files:**
{changed_files}

3. **File Contents:**
{file_contents}

4. **Test Results:**
{test_results}

5. **AST Analysis:**
{ast_analysis}

6. **Pattern Match Results:**
{pattern_match_results}

7. **GitHub Baseline (Notebook Repo):**
{github_evidence}

**Your Task:**
Analyze ALL evidence and determine if the student's code fulfills ALL requirements.

**Verification Checklist:**
1. ✅ Does the code implement what was asked?
2. ✅ Do the changes match the task requirements?
3. ✅ Do tests pass (if tests exist)?
4. ✅ Are required functions/classes present (from AST analysis)?
5. ✅ Do pattern matches indicate correct structure?
6. ✅ Is the code complete and functional?
7. ✅ Are there any critical issues?

**CRITICAL:**
- If tests exist and FAIL, the task MUST fail
- If required functions/classes are missing (from patterns), the task MUST fail
- If code has syntax errors, the task MUST fail
- Only pass if ALL requirements are met

**If FAILED, provide LeetCode-style hints:**
- Guide the student toward the solution
- Don't give direct answers
- Point out what's missing or incorrect
- Suggest approaches, not solutions

**Return ONLY valid JSON:**
{{
  "passed": true/false,
  "overall_feedback": "Brief summary (2-3 sentences) explaining if requirements are met",
  "requirements_check": {{
    "requirement_1": {{
      "met": true/false,
      "feedback": "Specific feedback on this requirement"
    }},
    "requirement_2": {{
      "met": true/false,
      "feedback": "Specific feedback on this requirement"
    }}
  }},
  "hints": ["hint1", "hint2"],  // Only if passed=false
  "issues_found": ["issue1", "issue2"],  // List of problems detected
  "suggestions": ["suggestion1", "suggestion2"],  // Improvement suggestions
  "code_quality": "good/acceptable/needs_improvement",
  "test_status": "passed/failed/not_run",  // From test results
  "pattern_match_status": "all_matched/partial/none"  // From pattern matching
}}

**CRITICAL JSON FORMATTING:**
- Return ONLY the JSON object, no markdown, no extra text
- Be specific about which requirements are met/not met
- Provide constructive feedback
- If passed=false, explain what's missing or incorrect
- Use hints to guide, not to give answers
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
            evidence: Evidence dict from VerificationEvidenceCollector
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

        # Format evidence for prompt
        git_diff = evidence.get("git_diff", "No git diff available")
        changed_files = "\n".join(evidence.get("changed_files", [])) or "No files changed"
        file_contents_str = self._format_file_contents(evidence.get("file_contents", {}))
        test_results_str = self._format_test_results(evidence.get("test_results"))
        ast_analysis_str = self._format_ast_analysis(evidence.get("ast_analysis", {}))
        pattern_match_str = self._format_pattern_match(evidence.get("pattern_match_results"))
        github_evidence_str = self._format_github_evidence(evidence.get("github_evidence"))

        # Build prompt
        prompt = VERIFICATION_PROMPT.format(
            task_description=task_description,
            task_requirements=task_requirements,
            git_diff=git_diff[:5000],  # Limit size
            changed_files=changed_files,
            file_contents=file_contents_str[:10000],  # Limit size
            test_results=test_results_str,
            ast_analysis=ast_analysis_str,
            pattern_match_results=pattern_match_str,
            github_evidence=github_evidence_str,
        )

        system_prompt = (
            "You are a STRICT code reviewer. "
            "Assume code is wrong unless proven correct. "
            "Return ONLY valid JSON object, no markdown, no extra text."
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
        """Format GitHub evidence for prompt."""
        if not github_evidence:
            return "No GitHub baseline available"

        repo_structure = github_evidence.get("repo_structure", [])
        files = github_evidence.get("files", {})

        parts = []
        if repo_structure:
            parts.append(f"Repository structure: {len(repo_structure)} items")
        if files:
            parts.append(f"Baseline files available: {', '.join(files.keys())}")

        return "\n".join(parts) if parts else "GitHub baseline available but empty"
