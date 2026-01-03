"""
API routes for roadmap content (read-only for users).
"""

from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from supabase import Client
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{project_id}")
async def get_roadmap(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get all days for a project with their status.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project belongs to user
        project_response = supabase.table("Projects").select("project_id").eq("project_id", project_id).eq("user_id", user_id).execute()
        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get all days
        days_response = supabase.table("roadmap_days").select("*").eq("project_id", project_id).order("day_number", desc=False).execute()
        
        return {
            "success": True,
            "days": days_response.data if days_response.data else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching roadmap: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch roadmap: {str(e)}")


@router.get("/{project_id}/day/{day_id}")
async def get_day_details(
    project_id: str,
    day_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get day details with all concepts (for Kanban board).
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project belongs to user
        project_response = supabase.table("Projects").select("project_id").eq("project_id", project_id).eq("user_id", user_id).execute()
        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get day
        day_response = supabase.table("roadmap_days").select("*").eq("day_id", day_id).eq("project_id", project_id).execute()
        if not day_response.data:
            raise HTTPException(status_code=404, detail="Day not found")
        
        day = day_response.data[0]
        
        # Get concepts for this day
        concepts_response = supabase.table("concepts").select("*").eq("day_id", day_id).order("order_index", desc=False).execute()
        concepts = concepts_response.data if concepts_response.data else []
        
        return {
            "success": True,
            "day": day,
            "concepts": concepts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching day details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch day details: {str(e)}")


@router.get("/{project_id}/concept/{concept_id}")
async def get_concept_details(
    project_id: str,
    concept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get concept details with subconcepts and tasks.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project belongs to user
        project_response = supabase.table("Projects").select("project_id").eq("project_id", project_id).eq("user_id", user_id).execute()
        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get concept
        concept_response = supabase.table("concepts").select("*").eq("concept_id", concept_id).execute()
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        concept = concept_response.data[0]
        
        # Get subconcepts
        subconcepts_response = supabase.table("sub_concepts").select("*").eq("concept_id", concept_id).order("order_index", desc=False).execute()
        subconcepts = subconcepts_response.data if subconcepts_response.data else []
        
        # Get tasks
        tasks_response = supabase.table("tasks").select("*").eq("concept_id", concept_id).order("order_index", desc=False).execute()
        tasks = tasks_response.data if tasks_response.data else []
        
        return {
            "success": True,
            "concept": concept,
            "subconcepts": subconcepts,
            "tasks": tasks
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching concept details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch concept details: {str(e)}")


@router.get("/{project_id}/generation-status")
async def get_generation_status(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get overall roadmap generation status.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project belongs to user
        project_response = supabase.table("Projects").select("project_id, target_days").eq("project_id", project_id).eq("user_id", user_id).execute()
        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = project_response.data[0]
        target_days = project["target_days"]
        
        # Count days by status
        days_response = supabase.table("roadmap_days").select("generated_status").eq("project_id", project_id).execute()
        days = days_response.data if days_response.data else []
        
        status_counts = {
            "pending": 0,
            "generating": 0,
            "generated": 0,
            "failed": 0,
        }
        
        for day in days:
            status = day.get("generated_status", "pending")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        total_days = len(days)
        generated_days = status_counts["generated"]
        is_complete = total_days == target_days and generated_days == target_days
        
        return {
            "success": True,
            "total_days": total_days,
            "target_days": target_days,
            "generated_days": generated_days,
            "status_counts": status_counts,
            "is_complete": is_complete,
            "is_generating": status_counts["generating"] > 0,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching generation status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch generation status: {str(e)}")


@router.get("/task/{task_id}")
async def get_task_details(
    task_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get task details with related concept and project information.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Get task
        task_response = supabase.table("tasks").select("*").eq("task_id", task_id).execute()
        if not task_response.data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        task = task_response.data[0]
        concept_id = task["concept_id"]
        
        # Get concept
        concept_response = supabase.table("concepts").select("*").eq("concept_id", concept_id).execute()
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        concept = concept_response.data[0]
        day_id = concept["day_id"]
        
        # Get day
        day_response = supabase.table("roadmap_days").select("*").eq("day_id", day_id).execute()
        if not day_response.data:
            raise HTTPException(status_code=404, detail="Day not found")
        
        day = day_response.data[0]
        project_id = day["project_id"]
        
        # Verify project belongs to user
        project_response = supabase.table("Projects").select("*").eq("project_id", project_id).eq("user_id", user_id).execute()
        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = project_response.data[0]
        
        return {
            "success": True,
            "task": task,
            "concept": concept,
            "day": day,
            "project": project
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching task details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch task details: {str(e)}")
