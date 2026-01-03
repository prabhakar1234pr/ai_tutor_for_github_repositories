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
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:47","message":"Day progress query result","data":{"user_id":user_id,"day_progress_count":len(day_progress_response.data or []),"day_progress_keys":list(day_progress.keys()),"day_progress_sample":list(day_progress.values())[:2] if day_progress else []},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"D"})+"\n")
        # #endregion
        
        # Repair: Check if Day 0 needs initialization or completion
        # Only run repair if Day 0 progress is missing or not "done" (skip if already complete)
        day0_response = supabase.table("roadmap_days").select("day_id, day_number").eq("project_id", project_id).eq("day_number", 0).execute()
        if day0_response.data:
            day0_id = day0_response.data[0]["day_id"]
            day0_progress = day_progress.get(day0_id)
            
            # Skip repair if Day 0 is already "done" - no need to check again
            if day0_progress and day0_progress.get("progress_status") == "done":
                # Day 0 is complete, skip repair to avoid unnecessary queries
                pass
            else:
                # Day 0 is missing or not "done", run repair
                # Get all concepts for Day 0
                concepts_response = supabase.table("concepts").select("concept_id").eq("day_id", day0_id).execute()
                concept_ids = [c["concept_id"] for c in (concepts_response.data or [])]
                
                if concept_ids:
                    # Get concept progress
                    concept_progress_response = supabase.table("user_concept_progress").select("concept_id, progress_status").eq("user_id", user_id).in_("concept_id", concept_ids).execute()
                    concept_progress_map = {p["concept_id"]: p["progress_status"] for p in (concept_progress_response.data or [])}
                    
                    # Also check subconcept and task progress to see if concept should be done
                    subconcepts_response = supabase.table("sub_concepts").select("subconcept_id").eq("concept_id", concept_ids[0]).execute()
                    subconcept_ids = [sc["subconcept_id"] for sc in (subconcepts_response.data or [])]
                    tasks_response = supabase.table("tasks").select("task_id").eq("concept_id", concept_ids[0]).execute()
                    task_ids = [t["task_id"] for t in (tasks_response.data or [])]
                    
                    subconcept_progress_response = supabase.table("user_subconcept_progress").select("subconcept_id, progress_status").eq("user_id", user_id).in_("subconcept_id", subconcept_ids if subconcept_ids else []).execute()
                    subconcept_progress_map = {p["subconcept_id"]: p["progress_status"] for p in (subconcept_progress_response.data or [])}
                    
                    task_progress_response = supabase.table("user_task_progress").select("task_id, progress_status").eq("user_id", user_id).in_("task_id", task_ids if task_ids else []).execute()
                    task_progress_map = {p["task_id"]: p["progress_status"] for p in (task_progress_response.data or [])}
                    
                    all_subconcepts_done = not subconcept_ids or all(subconcept_progress_map.get(sid) == "done" for sid in subconcept_ids)
                    all_tasks_done = not task_ids or all(task_progress_map.get(tid) == "done" for tid in task_ids)
                    
                    # Check if all concepts are done
                    all_concepts_done = all(
                        concept_progress_map.get(cid) == "done" for cid in concept_ids
                    )
                    
                    # #region agent log
                    import json
                    with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                        f.write(json.dumps({"location":"progress.py:70","message":"Repair: Checking Day 0 concept progress","data":{"day0_id":day0_id,"concept_ids":concept_ids,"concept_progress_map":concept_progress_map,"subconcept_ids":subconcept_ids,"task_ids":task_ids,"subconcept_progress_map":subconcept_progress_map,"task_progress_map":task_progress_map,"all_subconcepts_done":all_subconcepts_done,"all_tasks_done":all_tasks_done},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run2","hypothesisId":"B"})+"\n")
                    # #endregion
                    
                    # If concept is "doing" but all subconcepts and tasks are done, auto-complete it
                    if concept_progress_map.get(concept_ids[0]) == "doing" and all_subconcepts_done and all_tasks_done:
                        # #region agent log
                        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                            f.write(json.dumps({"location":"progress.py:95","message":"Repair: Auto-completing concept that should be done","data":{"concept_id":concept_ids[0]},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run2","hypothesisId":"B"})+"\n")
                        # #endregion
                        supabase.table("user_concept_progress").upsert({
                            "user_id": user_id,
                            "concept_id": concept_ids[0],
                            "progress_status": "done",
                            "updated_at": datetime.utcnow().isoformat(),
                        }, on_conflict="user_id,concept_id").execute()
                        # Update concept_progress_map for the check below
                        concept_progress_map[concept_ids[0]] = "done"
                        all_concepts_done = True
                    
                    # #region agent log
                    with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                        f.write(json.dumps({"location":"progress.py:75","message":"Repair: Day 0 completion check","data":{"all_concepts_done":all_concepts_done,"check_results":{cid:(concept_progress_map.get(cid) == "done") for cid in concept_ids},"day0_progress_status":day0_progress.get("progress_status") if day0_progress else None},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run2","hypothesisId":"B"})+"\n")
                    # #endregion
                    
                    # If Day 0 has no progress entry OR is "todo" but all concepts are done, repair it
                    if not day0_progress or (day0_progress and day0_progress.get("progress_status") != "done" and all_concepts_done):
                        if all_concepts_done:
                            # Day 0 is complete but missing progress entry or marked as todo - repair it
                            # #region agent log
                            with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                                f.write(json.dumps({"location":"progress.py:82","message":"Repair: Day 0 is complete, marking as done","data":{"day0_id":day0_id,"had_progress":bool(day0_progress)},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run2","hypothesisId":"B"})+"\n")
                            # #endregion
                            supabase.table("user_day_progress").upsert({
                                "user_id": user_id,
                                "day_id": day0_id,
                                "progress_status": "done",
                                "updated_at": datetime.utcnow().isoformat(),
                            }, on_conflict="user_id,day_id").execute()
                            
                            # Unlock Day 1
                            day1_response = supabase.table("roadmap_days").select("day_id").eq("project_id", project_id).eq("day_number", 1).execute()
                            if day1_response.data:
                                day1_id = day1_response.data[0]["day_id"]
                                supabase.table("user_day_progress").upsert({
                                    "user_id": user_id,
                                    "day_id": day1_id,
                                    "progress_status": "todo",
                                    "updated_at": datetime.utcnow().isoformat(),
                                }, on_conflict="user_id,day_id").execute()
                                # #region agent log
                                with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                                    f.write(json.dumps({"location":"progress.py:95","message":"Repair: Unlocked Day 1","data":{"day1_id":day1_id},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run2","hypothesisId":"B"})+"\n")
                                # #endregion
                            
                            # Refresh day_progress after repair
                            day_progress_response = supabase.table("user_day_progress").select("*").eq("user_id", user_id).execute()
                            day_progress = {p["day_id"]: p for p in (day_progress_response.data or [])}
                        elif not day0_progress:
                            # Day 0 not complete - initialize as "todo" if no progress exists
                            # #region agent log
                            with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                                f.write(json.dumps({"location":"progress.py:104","message":"Repair: Day 0 not complete, initializing as todo","data":{"day0_id":day0_id,"all_concepts_done":all_concepts_done},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run2","hypothesisId":"B"})+"\n")
                            # #endregion
                            supabase.table("user_day_progress").upsert({
                                "user_id": user_id,
                                "day_id": day0_id,
                                "progress_status": "todo",
                                "updated_at": datetime.utcnow().isoformat(),
                            }, on_conflict="user_id,day_id").execute()
                            # Refresh day_progress
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
        
        # #region agent log
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:67","message":"Returning progress data","data":{"day_progress_count":len(day_progress),"concept_progress_count":len(concept_progress)},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"D"})+"\n")
        # #endregion
        
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
        
        # Get day_id and check if all concepts for the day are done
        concept_response = supabase.table("concepts").select("day_id").eq("concept_id", concept_id).execute()
        if concept_response.data:
            day_id = concept_response.data[0]["day_id"]
            # Verify day belongs to project
            day_response = supabase.table("roadmap_days").select("project_id").eq("day_id", day_id).execute()
            if day_response.data and day_response.data[0]["project_id"] == project_id:
                await _check_and_complete_day_if_ready(supabase, user_id, day_id, project_id)
        
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


@router.post("/{project_id}/subconcept/{subconcept_id}/complete")
async def complete_subconcept(
    project_id: str,
    subconcept_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Mark subconcept as completed.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify subconcept exists and belongs to project
        subconcept_response = supabase.table("sub_concepts").select("subconcept_id, concept_id").eq("subconcept_id", subconcept_id).execute()
        if not subconcept_response.data:
            raise HTTPException(status_code=404, detail="Subconcept not found")
        
        subconcept = subconcept_response.data[0]
        
        # Verify concept belongs to project
        concept_response = supabase.table("concepts").select("concept_id, day_id").eq("concept_id", subconcept["concept_id"]).execute()
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        concept = concept_response.data[0]
        day_response = supabase.table("roadmap_days").select("project_id").eq("day_id", concept["day_id"]).execute()
        if not day_response.data or day_response.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Subconcept not found in project")
        
        # Check if progress record exists
        existing_response = supabase.table("user_subconcept_progress").select("id").eq("user_id", user_id).eq("subconcept_id", subconcept_id).execute()
        
        if existing_response.data and len(existing_response.data) > 0:
            # Update existing record
            supabase.table("user_subconcept_progress").update({
                "progress_status": "done",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).eq("subconcept_id", subconcept_id).execute()
        else:
            # Insert new record
            supabase.table("user_subconcept_progress").insert({
                "user_id": user_id,
                "subconcept_id": subconcept_id,
                "progress_status": "done",
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()
        
        # Check if all subconcepts and tasks for this concept are done, then auto-complete concept
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:401","message":"Calling _check_and_complete_concept_if_ready after subconcept completion","data":{"concept_id":subconcept["concept_id"],"user_id":user_id,"project_id":project_id},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
        # #endregion
        await _check_and_complete_concept_if_ready(supabase, user_id, subconcept["concept_id"], project_id)
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing subconcept: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete subconcept: {str(e)}")


@router.post("/{project_id}/task/{task_id}/complete")
async def complete_task(
    project_id: str,
    task_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Mark task as completed.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify task exists and belongs to project
        task_response = supabase.table("tasks").select("task_id, concept_id").eq("task_id", task_id).execute()
        if not task_response.data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        task = task_response.data[0]
        
        # Verify concept belongs to project
        concept_response = supabase.table("concepts").select("concept_id, day_id").eq("concept_id", task["concept_id"]).execute()
        if not concept_response.data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        concept = concept_response.data[0]
        day_response = supabase.table("roadmap_days").select("project_id").eq("day_id", concept["day_id"]).execute()
        if not day_response.data or day_response.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Task not found in project")
        
        # Check if progress record exists
        existing_response = supabase.table("user_task_progress").select("id").eq("user_id", user_id).eq("task_id", task_id).execute()
        
        if existing_response.data and len(existing_response.data) > 0:
            # Update existing record
            supabase.table("user_task_progress").update({
                "progress_status": "done",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).eq("task_id", task_id).execute()
        else:
            # Insert new record
            supabase.table("user_task_progress").insert({
                "user_id": user_id,
                "task_id": task_id,
                "progress_status": "done",
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()
        
        # Check if all subconcepts and tasks for this concept are done, then auto-complete concept
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:468","message":"Calling _check_and_complete_concept_if_ready after task completion","data":{"concept_id":task["concept_id"],"user_id":user_id,"project_id":project_id},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
        # #endregion
        await _check_and_complete_concept_if_ready(supabase, user_id, task["concept_id"], project_id)
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to complete task: {str(e)}")


async def _check_and_complete_concept_if_ready(supabase: Client, user_id: str, concept_id: str, project_id: str):
    """
    Helper function to check if all subconcepts and tasks for a concept are done,
    and if so, automatically complete the concept.
    Then check if all concepts for the day are done, and if so, complete the day and unlock next day.
    """
    try:
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:479","message":"_check_and_complete_concept_if_ready entry","data":{"concept_id":concept_id,"user_id":user_id},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
        # #endregion
        # Get all subconcepts for this concept
        subconcepts_response = supabase.table("sub_concepts").select("subconcept_id").eq("concept_id", concept_id).execute()
        subconcept_ids = [sc["subconcept_id"] for sc in (subconcepts_response.data or [])]
        
        # Get all tasks for this concept
        tasks_response = supabase.table("tasks").select("task_id").eq("concept_id", concept_id).execute()
        task_ids = [t["task_id"] for t in (tasks_response.data or [])]
        
        # #region agent log
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:492","message":"Found subconcepts and tasks","data":{"subconcept_count":len(subconcept_ids),"task_count":len(task_ids),"subconcept_ids":subconcept_ids,"task_ids":task_ids},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
        # #endregion
        
        # Check if all subconcepts are done
        all_subconcepts_done = True
        if subconcept_ids:
            subconcept_progress_response = supabase.table("user_subconcept_progress").select("subconcept_id, progress_status").eq("user_id", user_id).in_("subconcept_id", subconcept_ids).execute()
            subconcept_progress = {p["subconcept_id"]: p["progress_status"] for p in (subconcept_progress_response.data or [])}
            all_subconcepts_done = all(
                subconcept_progress.get(subconcept_id) == "done" 
                for subconcept_id in subconcept_ids
            )
            # #region agent log
            with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                f.write(json.dumps({"location":"progress.py:500","message":"Subconcept progress check","data":{"all_subconcepts_done":all_subconcepts_done,"subconcept_progress":subconcept_progress},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"C"})+"\n")
            # #endregion
        
        # Check if all tasks are done
        all_tasks_done = True
        if task_ids:
            task_progress_response = supabase.table("user_task_progress").select("task_id, progress_status").eq("user_id", user_id).in_("task_id", task_ids).execute()
            task_progress = {p["task_id"]: p["progress_status"] for p in (task_progress_response.data or [])}
            all_tasks_done = all(
                task_progress.get(task_id) == "done"
                for task_id in task_ids
            )
            # #region agent log
            with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                f.write(json.dumps({"location":"progress.py:509","message":"Task progress check","data":{"all_tasks_done":all_tasks_done,"task_progress":task_progress},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"C"})+"\n")
            # #endregion
        
        # If all subconcepts and tasks are done, complete the concept
        # If there are no subconcepts or tasks, consider it complete (empty concept)
        should_complete = False
        if not subconcept_ids and not task_ids:
            # Concept has no subconcepts or tasks, mark as complete
            should_complete = True
            logger.info(f"✅ Concept {concept_id} has no subconcepts/tasks, auto-completing")
        elif all_subconcepts_done and all_tasks_done:
            # All subconcepts and tasks are done
            should_complete = True
            logger.info(f"✅ All subconcepts and tasks completed for concept {concept_id}, auto-completing concept")
        
        # #region agent log
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:526","message":"Concept completion decision","data":{"should_complete":should_complete,"all_subconcepts_done":all_subconcepts_done,"all_tasks_done":all_tasks_done},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
        # #endregion
        
        if should_complete:
            supabase.table("user_concept_progress").upsert({
                "user_id": user_id,
                "concept_id": concept_id,
                "progress_status": "done",
                "updated_at": datetime.utcnow().isoformat(),
            }, on_conflict="user_id,concept_id").execute()
            
            # Now check if all concepts for the day are done
            concept_response = supabase.table("concepts").select("day_id").eq("concept_id", concept_id).execute()
            if concept_response.data:
                day_id = concept_response.data[0]["day_id"]
                # #region agent log
                with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                    f.write(json.dumps({"location":"progress.py:538","message":"Calling _check_and_complete_day_if_ready","data":{"day_id":day_id,"concept_id":concept_id},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
                # #endregion
                await _check_and_complete_day_if_ready(supabase, user_id, day_id, project_id)
    
    except Exception as e:
        logger.error(f"Error checking concept completion: {e}", exc_info=True)
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:541","message":"Error in _check_and_complete_concept_if_ready","data":{"error":str(e)},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"E"})+"\n")
        # #endregion
        # Don't raise - this is a helper function


async def _check_and_complete_day_if_ready(supabase: Client, user_id: str, day_id: str, project_id: str):
    """
    Helper function to check if all concepts for a day are done,
    and if so, automatically complete the day and unlock the next day.
    """
    try:
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:545","message":"_check_and_complete_day_if_ready entry","data":{"day_id":day_id,"user_id":user_id,"project_id":project_id},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
        # #endregion
        # Get all concepts for this day
        concepts_response = supabase.table("concepts").select("concept_id").eq("day_id", day_id).execute()
        concept_ids = [c["concept_id"] for c in (concepts_response.data or [])]
        
        # #region agent log
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:552","message":"Found concepts for day","data":{"concept_count":len(concept_ids),"concept_ids":concept_ids},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"C"})+"\n")
        # #endregion
        
        if not concept_ids:
            return
        
        # Check if all concepts are done
        concept_progress_response = supabase.table("user_concept_progress").select("concept_id, progress_status").eq("user_id", user_id).in_("concept_id", concept_ids).execute()
        concept_progress = {p["concept_id"]: p["progress_status"] for p in (concept_progress_response.data or [])}
        
        # #region agent log
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:559","message":"Concept progress for day","data":{"concept_progress":concept_progress,"concept_ids":concept_ids},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"C"})+"\n")
        # #endregion
        
        all_concepts_done = all(
            concept_progress.get(concept_id) == "done"
            for concept_id in concept_ids
        )
        
        # #region agent log
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:562","message":"All concepts done check","data":{"all_concepts_done":all_concepts_done,"check_results":{cid:(concept_progress.get(cid) == "done") for cid in concept_ids}},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"C"})+"\n")
        # #endregion
        
        # If all concepts are done, complete the day and unlock next day
        if all_concepts_done:
            logger.info(f"✅ All concepts completed for day {day_id}, auto-completing day")
            
            # Mark day as done
            supabase.table("user_day_progress").upsert({
                "user_id": user_id,
                "day_id": day_id,
                "progress_status": "done",
                "updated_at": datetime.utcnow().isoformat(),
            }, on_conflict="user_id,day_id").execute()
            
            # Get current day number and unlock next day
            day_response = supabase.table("roadmap_days").select("day_number").eq("day_id", day_id).execute()
            if day_response.data:
                current_day_number = day_response.data[0]["day_number"]
                next_day_number = current_day_number + 1
                
                # #region agent log
                with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                    f.write(json.dumps({"location":"progress.py:580","message":"Attempting to unlock next day","data":{"current_day_number":current_day_number,"next_day_number":next_day_number},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
                # #endregion
                
                # Unlock next day
                next_day_response = supabase.table("roadmap_days").select("day_id").eq("project_id", project_id).eq("day_number", next_day_number).execute()
                # #region agent log
                with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                    f.write(json.dumps({"location":"progress.py:586","message":"Next day query result","data":{"next_day_found":bool(next_day_response.data),"next_day_data":next_day_response.data if next_day_response.data else None},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
                # #endregion
                if next_day_response.data:
                    next_day_id = next_day_response.data[0]["day_id"]
                    supabase.table("user_day_progress").upsert({
                        "user_id": user_id,
                        "day_id": next_day_id,
                        "progress_status": "todo",
                        "updated_at": datetime.utcnow().isoformat(),
                    }, on_conflict="user_id,day_id").execute()
                    # #region agent log
                    with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
                        f.write(json.dumps({"location":"progress.py:589","message":"Next day unlocked successfully","data":{"next_day_id":next_day_id,"next_day_number":next_day_number},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"B"})+"\n")
                    # #endregion
                    logger.info(f"✅ Unlocked Day {next_day_number}")
    
    except Exception as e:
        logger.error(f"Error checking day completion: {e}", exc_info=True)
        # #region agent log
        import json
        with open('c:\\projects\\.cursor\\debug.log', 'a') as f:
            f.write(json.dumps({"location":"progress.py:600","message":"Error in _check_and_complete_day_if_ready","data":{"error":str(e)},"timestamp":int(__import__('time').time()*1000),"sessionId":"debug-session","runId":"run1","hypothesisId":"E"})+"\n")
        # #endregion
        # Don't raise - this is a helper function