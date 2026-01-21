"""
API routes for task verification.
Deep verification system using multi-layered evidence collection.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.llm_verifier import LLMVerifier
from app.services.verification_pipeline import get_verification_pipeline
from app.services.workspace_manager import WorkspaceManager
from app.utils.clerk_auth import verify_clerk_token

router = APIRouter()
logger = logging.getLogger(__name__)

# Task verification prompt template
TASK_VERIFICATION_PROMPT = """You are a code reviewer verifying if a student's code fulfills a task's requirements.

**Task Description:**
{task_description}

**Task Requirements:**
{task_requirements}

**User's Code:**
```{language}
{user_code}
```

**Your Task:**
Analyze the user's code and determine if it fulfills ALL requirements from the task description.

**Verification Criteria:**
1. Does the code implement what was asked?
2. Does it meet all specific requirements mentioned?
3. Does it produce the expected behavior/output?
4. Are there any critical issues that prevent it from working?

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
  "suggestions": ["suggestion1", "suggestion2"],
  "code_quality": "good/acceptable/needs_improvement"
}}

**CRITICAL:**
- Return ONLY the JSON object, no markdown, no extra text
- Be specific about which requirements are met/not met
- Provide constructive feedback
- If passed=false, explain what's missing or incorrect
"""


# ============================================
# Request/Response Models
# ============================================


class VerifyTaskRequest(BaseModel):
    """Request body for task verification."""

    workspace_id: str  # Workspace ID (changed from user_code)


class RequirementCheck(BaseModel):
    """Result of checking a single requirement."""

    met: bool
    feedback: str


class TaskVerificationResponse(BaseModel):
    """Response for task verification."""

    success: bool
    task_id: str
    passed: bool
    overall_feedback: str
    requirements_check: dict[str, RequirementCheck]
    hints: list[str]  # LeetCode-style hints (only if passed=False)
    issues_found: list[str]  # List of problems detected
    suggestions: list[str]  # Improvement suggestions
    code_quality: str
    test_status: str | None = None  # "passed"/"failed"/"not_run"
    pattern_match_status: str | None = None  # "all_matched"/"partial"/"none"


# ============================================
# API Endpoints
# ============================================


@router.post("/{task_id}/verify", response_model=TaskVerificationResponse)
async def verify_task(
    task_id: str,
    request: VerifyTaskRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Deep verification of task using multi-layered evidence collection.

    Collects evidence from:
    - Git diff and status
    - User's code state (file contents)
    - Test execution results
    - AST analysis
    - Pattern matching
    - GitHub API (notebook repo baseline)

    Uses LLM to make final verification decision with strict verification philosophy.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]

        # Get user_id
        user_response = (
            supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        )
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")

        user_id = user_response.data[0]["id"]

        # Get workspace
        workspace_manager = WorkspaceManager()
        workspace = workspace_manager.get_workspace(request.workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify workspace belongs to user
        if workspace.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this workspace")

        # Get task with description
        task_response = (
            supabase.table("tasks")
            .select("task_id, title, description, task_type, concept_id")
            .eq("task_id", task_id)
            .execute()
        )

        if not task_response.data:
            raise HTTPException(status_code=404, detail="Task not found")

        task = task_response.data[0]

        # Verify task belongs to user's project
        concept_response = (
            supabase.table("concepts")
            .select("concept_id, day_id")
            .eq("concept_id", task["concept_id"])
            .execute()
        )

        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")

        concept = concept_response.data[0]

        day_response = (
            supabase.table("roadmap_days")
            .select("project_id")
            .eq("day_id", concept["day_id"])
            .execute()
        )

        if not day_response.data:
            raise HTTPException(status_code=404, detail="Day not found")

        project_id = day_response.data[0]["project_id"]

        project_response = (
            supabase.table("projects")
            .select("project_id, github_access_token")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not project_response.data:
            raise HTTPException(status_code=403, detail="Not authorized to verify this task")

        # Get base commit from task session (if exists)
        base_commit = None
        try:
            from app.services.task_session_service import TaskSessionService

            session_service = TaskSessionService()
            task_session_result = session_service.get_task_session(
                task_id, user_id, request.workspace_id
            )
            if task_session_result.get("success"):
                session = task_session_result.get("session", {})
                base_commit = session.get("base_commit")
        except Exception as e:
            logger.warning(f"Could not get task session base_commit: {e}")

        # Extract task description and requirements
        task_description = task.get("description", "")
        task_requirements = task_description

        # Run multi-layered verification pipeline
        logger.info(f"🔍 Running verification pipeline for task {task_id}...")
        pipeline = get_verification_pipeline()
        verification_state = await pipeline.run_verification(
            task_id=task_id,
            workspace_id=request.workspace_id,
            base_commit=base_commit,
        )

        # Convert state to evidence dict for LLM
        evidence = pipeline.get_evidence_for_llm(verification_state)

        # Log pipeline results
        if verification_state.warnings:
            logger.warning(f"Pipeline warnings: {verification_state.warnings}")
        if verification_state.errors:
            logger.error(f"Pipeline errors: {verification_state.errors}")

        # Run LLM verification with all evidence
        logger.info("🤖 Running LLM verification with collected evidence...")
        llm_verifier = LLMVerifier()
        verification_result = await llm_verifier.verify_with_evidence(
            task_description=task_description,
            task_requirements=task_requirements,
            evidence=evidence,
            temperature=0.0,  # Strict mode
        )

        # Extract results
        passed = verification_result.get("passed", False)
        overall_feedback = verification_result.get("overall_feedback", "")
        requirements_check_raw = verification_result.get("requirements_check", {})
        hints = verification_result.get("hints", [])
        issues_found = verification_result.get("issues_found", [])
        suggestions = verification_result.get("suggestions", [])
        code_quality = verification_result.get("code_quality", "needs_improvement")
        test_status = verification_result.get("test_status")
        pattern_match_status = verification_result.get("pattern_match_status")

        # Convert requirements_check to proper format
        requirements_check: dict[str, RequirementCheck] = {}
        for req_name, req_data in requirements_check_raw.items():
            if isinstance(req_data, dict):
                requirements_check[req_name] = RequirementCheck(
                    met=req_data.get("met", False),
                    feedback=req_data.get("feedback", ""),
                )
            else:
                requirements_check[req_name] = RequirementCheck(
                    met=bool(req_data),
                    feedback="",
                )

        # If no requirements were checked, create a default one
        if not requirements_check:
            requirements_check["main_requirement"] = RequirementCheck(
                met=passed,
                feedback=overall_feedback,
            )

        logger.info(
            f"✅ Task verification complete: {'PASSED' if passed else 'FAILED'} "
            f"(quality: {code_quality}, test: {test_status}, patterns: {pattern_match_status})"
        )

        # Save verification results to database
        verification_status = "passed" if passed else "failed"
        await _save_verification_results(
            supabase=supabase,
            task_id=task_id,
            user_id=user_id,
            workspace_id=request.workspace_id,
            verification_status=verification_status,
            evidence=evidence,
            verification_result=verification_result,
            hints=hints,
        )

        # If verification passed, update memory ledger
        if passed:
            await _update_memory_ledger_on_task_pass(
                supabase=supabase,
                task_id=task_id,
                concept_id=task["concept_id"],
                evidence=evidence,
            )

        return TaskVerificationResponse(
            success=True,
            task_id=task_id,
            passed=passed,
            overall_feedback=overall_feedback,
            requirements_check=requirements_check,
            hints=hints,
            issues_found=issues_found,
            suggestions=suggestions,
            code_quality=code_quality,
            test_status=test_status,
            pattern_match_status=pattern_match_status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to verify task: {str(e)}") from e


async def _save_verification_results(
    supabase: Client,
    task_id: str,
    user_id: str,
    workspace_id: str,
    verification_status: str,
    evidence: dict,
    verification_result: dict,
    hints: list[str],
) -> None:
    """
    Save verification results to task_verification_results table.

    Stores all evidence and analysis for audit trail and debugging.
    """
    try:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()

        verification_record = {
            "task_id": task_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "verification_status": verification_status,
            "ast_analysis": evidence.get("ast_analysis", {}),
            "github_evidence": evidence.get("github_evidence", {}),
            "test_results": evidence.get("test_results", {}),
            "git_diff": evidence.get("git_diff", ""),
            "pattern_match_results": evidence.get("pattern_match_results", {}),
            "llm_analysis": verification_result,
            "hints": hints,
            "error_message": None,
            "verified_at": now,
            "created_at": now,
        }

        supabase.table("task_verification_results").insert(verification_record).execute()

        logger.debug(f"💾 Saved verification results for task {task_id}")

    except Exception as e:
        logger.error(f"Failed to save verification results: {e}", exc_info=True)
        # Don't fail verification if persistence fails


async def _update_memory_ledger_on_task_pass(
    supabase: Client,
    task_id: str,
    concept_id: str,
    evidence: dict,
) -> None:
    """
    Update memory ledger in database when task passes verification.

    Extracts files_touched and skills_unlocked from evidence and updates concepts table.
    """
    try:
        # Extract files_touched from evidence
        changed_files = evidence.get("changed_files", [])
        file_contents = evidence.get("file_contents", {})

        # Get files that were actually modified/created
        files_touched = list(set(changed_files + list(file_contents.keys())))

        # Extract skills from AST analysis (simplified - can be enhanced with LLM)
        ast_analysis = evidence.get("ast_analysis", {})
        skills_unlocked = []

        # Infer skills from code structure
        if ast_analysis.get("functions"):
            skills_unlocked.append("function_definition")
        if ast_analysis.get("classes"):
            skills_unlocked.append("class_definition")
        if ast_analysis.get("imports"):
            skills_unlocked.append("module_imports")

        # Get current concept data
        concept_response = (
            supabase.table("concepts")
            .select("files_touched, skills_unlocked")
            .eq("concept_id", concept_id)
            .execute()
        )

        if not concept_response.data:
            logger.warning(f"Concept {concept_id} not found, skipping memory ledger update")
            return

        concept = concept_response.data[0]
        existing_files = set(concept.get("files_touched") or [])
        existing_skills = set(concept.get("skills_unlocked") or [])

        # Merge new files and skills (avoid duplicates)
        updated_files = list(existing_files | set(files_touched))
        updated_skills = list(existing_skills | set(skills_unlocked))

        # Update concepts table
        supabase.table("concepts").update(
            {
                "files_touched": updated_files,
                "skills_unlocked": updated_skills,
            }
        ).eq("concept_id", concept_id).execute()

        logger.info(
            f"✅ Updated memory ledger for concept {concept_id}: "
            f"{len(updated_files)} files, {len(updated_skills)} skills"
        )

    except Exception as e:
        logger.error(f"Failed to update memory ledger: {e}", exc_info=True)
        # Don't fail verification if memory ledger update fails
