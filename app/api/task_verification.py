"""
API routes for task verification.
Verifies whether user's code fulfills task description requirements.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.groq_service import get_groq_service
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

    user_code: str
    language: str = "python"  # Default to python, can be "javascript", "typescript", etc.


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
    suggestions: list[str]
    code_quality: str


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
    Verify if user's code fulfills the task description requirements.

    Uses LLM to analyze the code against task requirements and provides
    detailed feedback on what's met and what's missing.
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
            .select("project_id")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not project_response.data:
            raise HTTPException(status_code=403, detail="Not authorized to verify this task")

        # Extract task description and requirements
        task_description = task.get("description", "")

        # Build requirements from description (extract key points)
        # The description should contain requirements, but we'll use the full description
        task_requirements = task_description

        # Call LLM for verification
        groq_service = get_groq_service()

        prompt = TASK_VERIFICATION_PROMPT.format(
            task_description=task_description,
            task_requirements=task_requirements,
            user_code=request.user_code,
            language=request.language,
        )

        system_prompt = (
            "You are an expert code reviewer. "
            "Return ONLY valid JSON object, no markdown, no extra text."
        )

        logger.info(f"🤖 Verifying task {task_id} with LLM...")

        llm_response = await groq_service.generate_response_async(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",
        )

        # Parse JSON response
        from app.utils.json_parser import parse_llm_json_response_async

        verification_result = await parse_llm_json_response_async(
            llm_response, expected_type="object"
        )

        # Extract results
        passed = verification_result.get("passed", False)
        overall_feedback = verification_result.get("overall_feedback", "")
        requirements_check_raw = verification_result.get("requirements_check", {})
        suggestions = verification_result.get("suggestions", [])
        code_quality = verification_result.get("code_quality", "needs_improvement")

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
            f"(quality: {code_quality})"
        )

        return TaskVerificationResponse(
            success=True,
            task_id=task_id,
            passed=passed,
            overall_feedback=overall_feedback,
            requirements_check=requirements_check,
            suggestions=suggestions,
            code_quality=code_quality,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to verify task: {str(e)}") from e
