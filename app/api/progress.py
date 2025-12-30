"""
API routes for user progress tracking.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from supabase import Client
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateProgressRequest(BaseModel):
    progress_status: str


@router.get("/{project_id}")
async def get_progress(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get user's progress across all days/concepts.
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
        
        # Get all day progress
        day_progress_response = supabase.table("user_day_progress").select("*").eq("user_id", user_id).execute()
        day_progress = {p["day_id"]: p for p in (day_progress_response.data or [])}
        
        # Get all concept progress
        concept_progress_response = supabase.table("user_concept_progress").select("*").eq("user_id", user_id).execute()
        concept_progress = {p["concept_id"]: p for p in (concept_progress_response.data or [])}
        
        # Get all subconcept progress
        subconcept_progress_response = supabase.table("user_subconcept_progress").select("*").eq("user_id", user_id).execute()
        subconcept_progress = {p["subconcept_id"]: p for p in (subconcept_progress_response.data or [])}
        
        # Get all task progress
        task_progress_response = supabase.table("user_task_progress").select("*").eq("user_id", user_id).execute()
        task_progress = {p["task_id"]: p for p in (task_progress_response.data or [])}
        
        return {
            "success": True,
            "day_progress": day_progress,
            "concept_progress": concept_progress,
            "subconcept_progress": subconcept_progress,
            "task_progress": task_progress,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching progress: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch progress: {str(e)}")


@router.get("/{project_id}/current")
async def get_current_progress(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Derive current day + concept from progress data.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Get all days for project
        days_response = supabase.table("roadmap_days").select("day_id, day_number").eq("project_id", project_id).order("day_number", desc=False).execute()
        days = days_response.data if days_response.data else []
        
        # Get day progress
        day_progress_response = supabase.table("user_day_progress").select("*").eq("user_id", user_id).execute()
        day_progress_map = {p["day_id"]: p for p in (day_progress_response.data or [])}
        
        # Find current day (highest "doing" or lowest "todo")
        current_day = None
        for day in days:
            progress = day_progress_map.get(day["day_id"])
            if progress and progress["progress_status"] == "doing":
                current_day = day
                break
        
        if not current_day:
            # Find first "todo" day
            for day in days:
                progress = day_progress_map.get(day["day_id"])
                if not progress or progress["progress_status"] == "todo":
                    current_day = day
                    break
        
        if not current_day and days:
            current_day = days[0]  # Default to first day
        
        current_concept = None
        if current_day:
            # Get concepts for current day
            concepts_response = supabase.table("concepts").select("concept_id, order_index, title").eq("day_id", current_day["day_id"]).order("order_index", desc=False).execute()
            concepts = concepts_response.data if concepts_response.data else []
            
            # Get concept progress
            concept_progress_response = supabase.table("user_concept_progress").select("*").eq("user_id", user_id).execute()
            concept_progress_map = {p["concept_id"]: p for p in (concept_progress_response.data or [])}
            
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch current progress: {str(e)}")


@router.post("/{project_id}/concept/{concept_id}/start")
async def start_concept(
    project_id: str,
    concept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Move concept to "doing" status.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify concept exists and belongs to project
        concept_response = supabase.table("concepts").select("concept_id, day_id").eq("concept_id", concept_id).execute()
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        concept = concept_response.data[0]
        
        # Verify day belongs to project
        day_response = supabase.table("roadmap_days").select("project_id").eq("day_id", concept["day_id"]).execute()
        if not day_response.data or day_response.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Concept not found in project")
        
        # Upsert progress
        supabase.table("user_concept_progress").upsert({
            "user_id": user_id,
            "concept_id": concept_id,
            "progress_status": "doing",
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,concept_id").execute()
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting concept: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start concept: {str(e)}")


@router.post("/{project_id}/concept/{concept_id}/complete")
async def complete_concept(
    project_id: str,
    concept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Move concept to "done" status.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Upsert progress
        supabase.table("user_concept_progress").upsert({
            "user_id": user_id,
            "concept_id": concept_id,
            "progress_status": "done",
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,concept_id").execute()
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing concept: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete concept: {str(e)}")


@router.post("/{project_id}/day/{day_id}/start")
async def start_day(
    project_id: str,
    day_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Start a day (move to "doing").
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Upsert progress
        supabase.table("user_day_progress").upsert({
            "user_id": user_id,
            "day_id": day_id,
            "progress_status": "doing",
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,day_id").execute()
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting day: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start day: {str(e)}")


@router.post("/{project_id}/day/{day_id}/complete")
async def complete_day(
    project_id: str,
    day_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Complete a day and unlock next day.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Mark day as done
        supabase.table("user_day_progress").upsert({
            "user_id": user_id,
            "day_id": day_id,
            "progress_status": "done",
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,day_id").execute()
        
        # Get current day number
        day_response = supabase.table("roadmap_days").select("day_number").eq("day_id", day_id).execute()
        if day_response.data:
            current_day_number = day_response.data[0]["day_number"]
            next_day_number = current_day_number + 1
            
            # Unlock next day
            next_day_response = supabase.table("roadmap_days").select("day_id").eq("project_id", project_id).eq("day_number", next_day_number).execute()
            if next_day_response.data:
                next_day_id = next_day_response.data[0]["day_id"]
                supabase.table("user_day_progress").upsert({
                    "user_id": user_id,
                    "day_id": next_day_id,
                    "progress_status": "todo",
                    "updated_at": datetime.utcnow().isoformat(),
                }, on_conflict="user_id,day_id").execute()
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing day: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete day: {str(e)}")

