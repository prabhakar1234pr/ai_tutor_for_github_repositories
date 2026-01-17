"""
API routes for user progress tracking.
Handles day, concept, and task progress with analytics timestamps.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateProgressRequest(BaseModel):
    progress_status: str


@router.get("/{project_id}")
async def get_progress(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get user's progress across all days, concepts, and tasks.
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

        # Verify project belongs to user
        project_response = (
            supabase.table("projects")
            .select("project_id")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get all day progress
        day_progress_response = (
            supabase.table("user_day_progress").select("*").eq("user_id", user_id).execute()
        )
        day_progress = {p["day_id"]: p for p in (day_progress_response.data or [])}

        # Initialize Day 0 if needed
        day0_response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number")
            .eq("project_id", project_id)
            .eq("day_number", 0)
            .execute()
        )
        if day0_response.data:
            day0_id = day0_response.data[0]["day_id"]
            day0_progress = day_progress.get(day0_id)

            if not day0_progress:
                # Initialize Day 0 as "todo"
                supabase.table("user_day_progress").upsert(
                    {
                        "user_id": user_id,
                        "day_id": day0_id,
                        "progress_status": "todo",
                        "updated_at": datetime.now(UTC).isoformat(),
                    },
                    on_conflict="user_id,day_id",
                ).execute()

                # Refresh day_progress
                day_progress_response = (
                    supabase.table("user_day_progress").select("*").eq("user_id", user_id).execute()
                )
                day_progress = {p["day_id"]: p for p in (day_progress_response.data or [])}

        # Get all concept progress
        concept_progress_response = (
            supabase.table("user_concept_progress").select("*").eq("user_id", user_id).execute()
        )
        concept_progress = {p["concept_id"]: p for p in (concept_progress_response.data or [])}

        # Get all task progress
        task_progress_response = (
            supabase.table("user_task_progress").select("*").eq("user_id", user_id).execute()
        )
        task_progress = {p["task_id"]: p for p in (task_progress_response.data or [])}

        return {
            "success": True,
            "day_progress": day_progress,
            "concept_progress": concept_progress,
            "task_progress": task_progress,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching progress: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch progress: {str(e)}") from e


@router.get("/{project_id}/current")
async def get_current_progress(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Derive current day + concept from progress data.
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

        # Get all days for project
        days_response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number, estimated_minutes")
            .eq("project_id", project_id)
            .order("day_number", desc=False)
            .execute()
        )
        days = days_response.data if days_response.data else []

        # Get day progress
        day_progress_response = (
            supabase.table("user_day_progress").select("*").eq("user_id", user_id).execute()
        )
        day_progress_map = {p["day_id"]: p for p in (day_progress_response.data or [])}

        # Find current day (highest "doing" or lowest "todo")
        current_day = None
        for day in days:
            progress = day_progress_map.get(day["day_id"])
            if progress and progress["progress_status"] == "doing":
                current_day = day
                break

        if not current_day:
            for day in days:
                progress = day_progress_map.get(day["day_id"])
                if not progress or progress["progress_status"] == "todo":
                    current_day = day
                    break

        if not current_day and days:
            current_day = days[0]

        current_concept = None
        if current_day:
            # Get concepts for current day
            concepts_response = (
                supabase.table("concepts")
                .select("concept_id, order_index, title, estimated_minutes")
                .eq("day_id", current_day["day_id"])
                .order("order_index", desc=False)
                .execute()
            )
            concepts = concepts_response.data if concepts_response.data else []

            # Get concept progress
            concept_progress_response = (
                supabase.table("user_concept_progress").select("*").eq("user_id", user_id).execute()
            )
            concept_progress_map = {
                p["concept_id"]: p for p in (concept_progress_response.data or [])
            }

            # Find current concept
            for concept in concepts:
                progress = concept_progress_map.get(concept["concept_id"])
                if progress and progress["progress_status"] == "doing":
                    current_concept = concept
                    break

            if not current_concept:
                for concept in concepts:
                    progress = concept_progress_map.get(concept["concept_id"])
                    if not progress or progress["progress_status"] == "todo":
                        current_concept = concept
                        break

        return {
            "success": True,
            "current_day": current_day,
            "current_concept": current_concept,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching current progress: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch current progress: {str(e)}"
        ) from e


@router.post("/{project_id}/concept/{concept_id}/start")
async def start_concept(
    project_id: str,
    concept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Move concept to "doing" status and record start time.
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

        # Verify concept exists and belongs to project
        concept_response = (
            supabase.table("concepts")
            .select("concept_id, day_id")
            .eq("concept_id", concept_id)
            .execute()
        )
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")

        concept = concept_response.data[0]

        # Verify day belongs to project
        day_response = (
            supabase.table("roadmap_days")
            .select("project_id")
            .eq("day_id", concept["day_id"])
            .execute()
        )
        if not day_response.data or day_response.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Concept not found in project")

        now = datetime.now(UTC).isoformat()

        # Upsert progress with started_at timestamp
        supabase.table("user_concept_progress").upsert(
            {
                "user_id": user_id,
                "concept_id": concept_id,
                "progress_status": "doing",
                "started_at": now,
                "updated_at": now,
            },
            on_conflict="user_id,concept_id",
        ).execute()

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting concept: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start concept: {str(e)}") from e


@router.post("/{project_id}/concept/{concept_id}/complete")
async def complete_concept(
    project_id: str,
    concept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Move concept to "done" status and record completion time.
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

        now = datetime.now(UTC).isoformat()

        # Upsert progress with completed_at timestamp
        supabase.table("user_concept_progress").upsert(
            {
                "user_id": user_id,
                "concept_id": concept_id,
                "progress_status": "done",
                "completed_at": now,
                "updated_at": now,
            },
            on_conflict="user_id,concept_id",
        ).execute()

        # Check if all concepts for the day are done
        concept_response = (
            supabase.table("concepts").select("day_id").eq("concept_id", concept_id).execute()
        )
        if concept_response.data:
            day_id = concept_response.data[0]["day_id"]
            day_response = (
                supabase.table("roadmap_days").select("project_id").eq("day_id", day_id).execute()
            )
            if day_response.data and day_response.data[0]["project_id"] == project_id:
                await _check_and_complete_day_if_ready(supabase, user_id, day_id, project_id)

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing concept: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete concept: {str(e)}") from e


@router.post("/{project_id}/concept/{concept_id}/content-read")
async def mark_content_read(
    project_id: str,
    concept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Mark concept content as read by the user.
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

        # Verify concept exists and belongs to project
        concept_response = (
            supabase.table("concepts")
            .select("concept_id, day_id")
            .eq("concept_id", concept_id)
            .execute()
        )
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")

        concept = concept_response.data[0]

        # Verify day belongs to project
        day_response = (
            supabase.table("roadmap_days")
            .select("project_id")
            .eq("day_id", concept["day_id"])
            .execute()
        )
        if not day_response.data or day_response.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Concept not found in project")

        now = datetime.now(UTC).isoformat()

        # Check if progress record already exists
        existing = (
            supabase.table("user_concept_progress")
            .select("progress_status")
            .eq("user_id", user_id)
            .eq("concept_id", concept_id)
            .execute()
        )

        if existing.data:
            # Update only content_read flag
            supabase.table("user_concept_progress").update(
                {
                    "content_read": True,
                    "updated_at": now,
                }
            ).eq("user_id", user_id).eq("concept_id", concept_id).execute()
        else:
            # Insert new record with required fields
            supabase.table("user_concept_progress").insert(
                {
                    "user_id": user_id,
                    "concept_id": concept_id,
                    "content_read": True,
                    "progress_status": "doing",
                    "updated_at": now,
                }
            ).execute()

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking content as read: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to mark content as read: {str(e)}"
        ) from e


@router.post("/{project_id}/day/{day_id}/start")
async def start_day(
    project_id: str,
    day_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Start a day (move to "doing") and record start time.
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

        now = datetime.now(UTC).isoformat()

        # Upsert progress with started_at timestamp
        supabase.table("user_day_progress").upsert(
            {
                "user_id": user_id,
                "day_id": day_id,
                "progress_status": "doing",
                "started_at": now,
                "updated_at": now,
            },
            on_conflict="user_id,day_id",
        ).execute()

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting day: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start day: {str(e)}") from e


@router.post("/{project_id}/day/{day_id}/complete")
async def complete_day(
    project_id: str,
    day_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Complete a day and unlock next day.
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

        now = datetime.now(UTC).isoformat()

        # Mark day as done with completed_at timestamp
        supabase.table("user_day_progress").upsert(
            {
                "user_id": user_id,
                "day_id": day_id,
                "progress_status": "done",
                "completed_at": now,
                "updated_at": now,
            },
            on_conflict="user_id,day_id",
        ).execute()

        # Get current day number
        day_response = (
            supabase.table("roadmap_days").select("day_number").eq("day_id", day_id).execute()
        )
        if day_response.data:
            current_day_number = day_response.data[0]["day_number"]
            next_day_number = current_day_number + 1

            # Unlock next day
            next_day_response = (
                supabase.table("roadmap_days")
                .select("day_id")
                .eq("project_id", project_id)
                .eq("day_number", next_day_number)
                .execute()
            )
            if next_day_response.data:
                next_day_id = next_day_response.data[0]["day_id"]
                supabase.table("user_day_progress").upsert(
                    {
                        "user_id": user_id,
                        "day_id": next_day_id,
                        "progress_status": "todo",
                        "updated_at": now,
                    },
                    on_conflict="user_id,day_id",
                ).execute()

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing day: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete day: {str(e)}") from e


class CompleteTaskRequest(BaseModel):
    github_username: str | None = None  # For github_profile task
    user_repo_url: str | None = None  # For create_repo task
    commit_sha: str | None = None  # For verify_commit task


@router.post("/{project_id}/task/{task_id}/complete")
async def complete_task(
    project_id: str,
    task_id: str,
    request: CompleteTaskRequest | None = None,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Mark task as completed and record completion time.
    Optionally stores project-specific data (repo_url, commit_sha) for Day 0 tasks.
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

        # Verify task exists and belongs to project
        task_response = (
            supabase.table("tasks")
            .select("task_id, concept_id, task_type")
            .eq("task_id", task_id)
            .execute()
        )
        if not task_response.data:
            raise HTTPException(status_code=404, detail="Task not found")

        task = task_response.data[0]
        task_type = task.get("task_type")

        # Verify concept belongs to project
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
        if not day_response.data or day_response.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Task not found in project")

        now = datetime.now(UTC).isoformat()

        # Check if progress record exists
        existing_response = (
            supabase.table("user_task_progress")
            .select("id, started_at")
            .eq("user_id", user_id)
            .eq("task_id", task_id)
            .execute()
        )

        if existing_response.data and len(existing_response.data) > 0:
            # Update existing record
            supabase.table("user_task_progress").update(
                {
                    "progress_status": "done",
                    "completed_at": now,
                    "updated_at": now,
                }
            ).eq("user_id", user_id).eq("task_id", task_id).execute()
        else:
            # Insert new record
            supabase.table("user_task_progress").insert(
                {
                    "user_id": user_id,
                    "task_id": task_id,
                    "progress_status": "done",
                    "started_at": now,
                    "completed_at": now,
                    "updated_at": now,
                }
            ).execute()

        # Store project-specific data for Day 0 tasks
        project_updates = {}
        if request:
            if task_type == "github_profile" and request.github_username:
                project_updates["github_username"] = request.github_username
                logger.info(
                    f"Storing github_username for project {project_id}: {request.github_username}"
                )
            elif task_type == "create_repo" and request.user_repo_url:
                project_updates["user_repo_url"] = request.user_repo_url
                logger.info(
                    f"Storing user_repo_url for project {project_id}: {request.user_repo_url}"
                )
            elif task_type == "verify_commit" and request.commit_sha:
                project_updates["user_repo_first_commit"] = request.commit_sha
                logger.info(
                    f"Storing user_repo_first_commit for project {project_id}: {request.commit_sha}"
                )

        if project_updates:
            supabase.table("projects").update(project_updates).eq("project_id", project_id).eq(
                "user_id", user_id
            ).execute()

        # Check if all tasks for this concept are done, then auto-complete concept
        await _check_and_complete_concept_if_ready(
            supabase, user_id, task["concept_id"], project_id
        )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete task: {str(e)}") from e


@router.post("/{project_id}/task/{task_id}/start")
async def start_task(
    project_id: str,
    task_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Start a task and record start time.
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

        now = datetime.now(UTC).isoformat()

        # Check if progress record exists
        existing_response = (
            supabase.table("user_task_progress")
            .select("id")
            .eq("user_id", user_id)
            .eq("task_id", task_id)
            .execute()
        )

        if existing_response.data and len(existing_response.data) > 0:
            # Update existing record
            supabase.table("user_task_progress").update(
                {
                    "progress_status": "doing",
                    "started_at": now,
                    "updated_at": now,
                }
            ).eq("user_id", user_id).eq("task_id", task_id).execute()
        else:
            # Insert new record
            supabase.table("user_task_progress").insert(
                {
                    "user_id": user_id,
                    "task_id": task_id,
                    "progress_status": "doing",
                    "started_at": now,
                    "updated_at": now,
                }
            ).execute()

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start task: {str(e)}") from e


async def _check_and_complete_concept_if_ready(
    supabase: Client, user_id: str, concept_id: str, project_id: str
):
    """
    Check if all tasks for a concept are done and content is read.
    If so, automatically complete the concept and check if day should be completed.
    """
    try:
        # Get all tasks for this concept
        tasks_response = (
            supabase.table("tasks").select("task_id").eq("concept_id", concept_id).execute()
        )
        task_ids = [t["task_id"] for t in (tasks_response.data or [])]

        # Get concept progress to check content_read
        concept_progress_response = (
            supabase.table("user_concept_progress")
            .select("content_read")
            .eq("user_id", user_id)
            .eq("concept_id", concept_id)
            .execute()
        )
        content_read = False
        if concept_progress_response.data:
            content_read = concept_progress_response.data[0].get("content_read", False)

        # Check if all tasks are done
        all_tasks_done = True
        if task_ids:
            task_progress_response = (
                supabase.table("user_task_progress")
                .select("task_id, progress_status")
                .eq("user_id", user_id)
                .in_("task_id", task_ids)
                .execute()
            )
            task_progress = {
                p["task_id"]: p["progress_status"] for p in (task_progress_response.data or [])
            }
            all_tasks_done = all(task_progress.get(task_id) == "done" for task_id in task_ids)

        # Auto-complete concept if content is read AND all tasks are done
        should_complete = False
        if not task_ids and content_read:
            # No tasks, just need content read
            should_complete = True
            logger.info(f"✅ Concept {concept_id} content read with no tasks, auto-completing")
        elif all_tasks_done and content_read:
            # All tasks done and content read
            should_complete = True
            logger.info(
                f"✅ All tasks completed and content read for concept {concept_id}, auto-completing"
            )
        elif all_tasks_done and not task_ids:
            # No tasks and no content requirement (edge case)
            should_complete = True
            logger.info(f"✅ Concept {concept_id} has no tasks, auto-completing")

        if should_complete:
            now = datetime.now(UTC).isoformat()
            supabase.table("user_concept_progress").upsert(
                {
                    "user_id": user_id,
                    "concept_id": concept_id,
                    "progress_status": "done",
                    "completed_at": now,
                    "updated_at": now,
                },
                on_conflict="user_id,concept_id",
            ).execute()

            # Check if all concepts for the day are done
            concept_response = (
                supabase.table("concepts").select("day_id").eq("concept_id", concept_id).execute()
            )
            if concept_response.data:
                day_id = concept_response.data[0]["day_id"]
                await _check_and_complete_day_if_ready(supabase, user_id, day_id, project_id)

    except Exception as e:
        logger.error(f"Error checking concept completion: {e}", exc_info=True)


async def _check_and_complete_day_if_ready(
    supabase: Client, user_id: str, day_id: str, project_id: str
):
    """
    Check if all concepts for a day are done.
    If so, automatically complete the day and unlock the next day.
    """
    try:
        # Get all concepts for this day
        concepts_response = (
            supabase.table("concepts").select("concept_id").eq("day_id", day_id).execute()
        )
        concept_ids = [c["concept_id"] for c in (concepts_response.data or [])]

        if not concept_ids:
            return

        # Check if all concepts are done
        concept_progress_response = (
            supabase.table("user_concept_progress")
            .select("concept_id, progress_status")
            .eq("user_id", user_id)
            .in_("concept_id", concept_ids)
            .execute()
        )
        concept_progress = {
            p["concept_id"]: p["progress_status"] for p in (concept_progress_response.data or [])
        }

        all_concepts_done = all(
            concept_progress.get(concept_id) == "done" for concept_id in concept_ids
        )

        if all_concepts_done:
            logger.info(f"✅ All concepts completed for day {day_id}, auto-completing day")

            now = datetime.now(UTC).isoformat()

            # Mark day as done
            supabase.table("user_day_progress").upsert(
                {
                    "user_id": user_id,
                    "day_id": day_id,
                    "progress_status": "done",
                    "completed_at": now,
                    "updated_at": now,
                },
                on_conflict="user_id,day_id",
            ).execute()

            # Get current day number and unlock next day
            day_response = (
                supabase.table("roadmap_days").select("day_number").eq("day_id", day_id).execute()
            )
            if day_response.data:
                current_day_number = day_response.data[0]["day_number"]
                next_day_number = current_day_number + 1

                # Unlock next day
                next_day_response = (
                    supabase.table("roadmap_days")
                    .select("day_id")
                    .eq("project_id", project_id)
                    .eq("day_number", next_day_number)
                    .execute()
                )
                if next_day_response.data:
                    next_day_id = next_day_response.data[0]["day_id"]
                    supabase.table("user_day_progress").upsert(
                        {
                            "user_id": user_id,
                            "day_id": next_day_id,
                            "progress_status": "todo",
                            "updated_at": now,
                        },
                        on_conflict="user_id,day_id",
                    ).execute()
                    logger.info(f"✅ Unlocked Day {next_day_number}")

    except Exception as e:
        logger.error(f"Error checking day completion: {e}", exc_info=True)
