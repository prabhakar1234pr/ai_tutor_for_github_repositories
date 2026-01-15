"""
Database operations for saving roadmap content.
All nodes that write to Supabase database.
Saves concepts with content field and tasks with new fields (difficulty, hints, estimated_minutes).
"""

import logging
from typing import Dict, List
from app.agents.state import RoadmapAgentState, DayTheme, ConceptData
from app.core.supabase_client import get_supabase_client
# Day 0 is handled separately via API endpoint, not imported here
from app.utils.markdown_sanitizer import sanitize_markdown_content
import httpx

logger = logging.getLogger(__name__)

# Import postgrest exception if available
try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except ImportError:
    PostgrestAPIError = Exception


def insert_all_days_to_db(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Insert all day themes into roadmap_days table (Days 1-N only).
    Day 0 is handled separately via API endpoint (initialize-day0).
    Includes estimated_minutes for each day.
    """
    project_id = state["project_id"]
    curriculum = state.get("curriculum", [])
    target_days = state["target_days"]
    
    logger.info(f"💾 Inserting {len(curriculum)} days (Days 1-{target_days}) into database...")
    logger.info(f"   Note: Day 0 is handled separately via API endpoint")
    
    supabase = get_supabase_client()
    
    # Prepare all days to insert (Days 1-N only, Day 0 excluded)
    days_to_insert = []
    
    # Days 1 to target_days (from curriculum)
    for theme in curriculum:
        days_to_insert.append({
            "project_id": project_id,
            "day_number": theme["day_number"],
            "theme": theme["theme"],
            "description": theme["description"],
            "estimated_minutes": theme.get("estimated_minutes", 60),
            "generated_status": "pending",
        })
    
    # Insert all days
    try:
        if not days_to_insert:
            logger.warning("⚠️  No days to insert (curriculum is empty)")
            state["day_ids_map"] = {}
            return state
        
        response = supabase.table("roadmap_days").insert(days_to_insert).execute()
        
        if not response.data:
            raise ValueError("Failed to insert days into database")
        
        # Store day_ids in state
        day_ids_map: Dict[int, str] = {}
        for day_data in response.data:
            day_number = day_data["day_number"]
            day_id = day_data["day_id"]
            day_ids_map[day_number] = day_id
        
        logger.info(f"✅ Inserted {len(response.data)} days (Days 1-{target_days}) into database")
        
        state["day_ids_map"] = day_ids_map
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to insert days: {e}", exc_info=True)
        state["error"] = f"Failed to insert days: {str(e)}"
        return state


# Note: save_day0_content has been removed - Day 0 is now handled via API endpoint (initialize-day0)

def save_concepts_to_db(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Save concept titles to database (before generating content/tasks).
    """
    day_id = state.get("current_day_id")
    current_concepts = state.get("current_concepts", [])
    
    if not day_id:
        raise ValueError("current_day_id not found in state")
    
    if not current_concepts:
        raise ValueError("current_concepts is empty")
    
    logger.info(f"💾 Saving {len(current_concepts)} concepts to database...")
    
    supabase = get_supabase_client()
    
    try:
        # Insert concepts with generating status
        concepts_to_insert = []
        for concept in current_concepts:
            concepts_to_insert.append({
                "day_id": day_id,
                "order_index": concept["order_index"],
                "title": concept["title"],
                "description": concept.get("description", ""),
                "estimated_minutes": concept.get("estimated_minutes", 10),
                "generated_status": "generating",
            })
        
        response = supabase.table("concepts").insert(concepts_to_insert).execute()
        
        if not response.data:
            raise ValueError("Failed to insert concepts")
        
        # Store concept_ids in state
        concept_ids_map: Dict[int, str] = {}
        for concept_data in response.data:
            order_idx = concept_data["order_index"]
            concept_id = concept_data["concept_id"]
            concept_ids_map[order_idx] = concept_id
        
        logger.info(f"✅ Inserted {len(response.data)} concepts")
        
        state["concept_ids_map"] = concept_ids_map
        state["current_concept_index"] = 0
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to save concepts: {e}", exc_info=True)
        state["error"] = f"Failed to save concepts: {str(e)}"
        return state


def save_concept_content(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Save content and tasks for the current concept.
    Content is saved directly to the concept, not to sub_concepts table.
    """
    current_concepts = state.get("current_concepts", [])
    current_concept_index = state.get("current_concept_index", 0)
    concept_ids_map = state.get("concept_ids_map") or {}
    
    if current_concept_index >= len(current_concepts):
        logger.warning("⚠️  No more concepts to save")
        return state
    
    concept = current_concepts[current_concept_index]
    concept_id = concept_ids_map.get(concept["order_index"])
    
    if not concept_id:
        raise ValueError(f"Concept ID not found for order_index {concept['order_index']}")
    
    logger.info(f"💾 Saving content for concept: {concept['title']}")
    
    supabase = get_supabase_client()
    
    try:
        # Update concept with content (sanitize markdown before saving)
        raw_content = concept.get("content", "")
        content = sanitize_markdown_content(raw_content)
        estimated_minutes = concept.get("estimated_minutes", 10)
        
        supabase.table("concepts").update({
            "content": content,
            "estimated_minutes": estimated_minutes,
            "generated_status": "generated",
        }).eq("concept_id", concept_id).execute()
        
        # Insert tasks
        if concept.get("tasks"):
            tasks_to_insert = []
            for task in concept["tasks"]:
                if not isinstance(task, dict):
                    logger.warning(f"⚠️  Skipping invalid task (type: {type(task).__name__})")
                    continue
                
                try:
                    tasks_to_insert.append({
                        "concept_id": concept_id,
                        "order_index": int(task.get("order_index", 0)),
                        "title": str(task.get("title", "")),
                        "description": str(task.get("description", "")),
                        "task_type": str(task.get("task_type", "coding")),
                        "estimated_minutes": int(task.get("estimated_minutes", 15)),
                        "difficulty": str(task.get("difficulty", "medium")),
                        "hints": task.get("hints", []),
                        "solution": task.get("solution"),
                        "generated_status": "generated",
                    })
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"⚠️  Error processing task: {e}, skipping")
                    continue
            
            if tasks_to_insert:
                try:
                    supabase.table("tasks").insert(tasks_to_insert).execute()
                    logger.debug(f"   Inserted {len(tasks_to_insert)} tasks")
                except PostgrestAPIError as db_error:
                    error_msg = str(db_error)
                    if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
                        logger.warning(f"⚠️  Duplicate tasks detected, skipping")
                    else:
                        raise
                except httpx.HTTPStatusError as http_error:
                    if http_error.response.status_code == 429:
                        logger.warning(f"⚠️  Rate limit hit, will retry later")
                        supabase.table("concepts").update({
                            "generated_status": "generating_with_errors"
                        }).eq("concept_id", concept_id).execute()
                        state["current_concept_index"] = current_concept_index + 1
                        return state
                    else:
                        raise
        
        logger.info(f"✅ Concept content saved: {concept['title']}")
        
        # Increment concept index
        state["current_concept_index"] = current_concept_index + 1
        
        return state
        
    except (PostgrestAPIError, httpx.HTTPStatusError, httpx.RemoteProtocolError) as e:
        error_msg = str(e)
        logger.error(f"❌ Database error for concept '{concept['title']}': {e}")
        try:
            supabase.table("concepts").update({
                "generated_status": "generated_with_errors"
            }).eq("concept_id", concept_id).execute()
        except:
            pass
        state["current_concept_index"] = current_concept_index + 1
        return state
    except Exception as e:
        logger.error(f"❌ Unexpected error for concept '{concept['title']}': {e}", exc_info=True)
        try:
            supabase.table("concepts").update({
                "generated_status": "generated_with_errors"
            }).eq("concept_id", concept_id).execute()
        except:
            pass
        state["current_concept_index"] = current_concept_index + 1
        return state


def mark_day_generated(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Mark the current day as fully generated.
    """
    day_id = state.get("current_day_id")
    current_day_number = state.get("current_day_number", 0)
    
    if not day_id:
        raise ValueError("current_day_id not found in state")
    
    logger.info(f"✅ Marking Day {current_day_number} as generated...")
    
    supabase = get_supabase_client()
    
    try:
        supabase.table("roadmap_days").update({
            "generated_status": "generated"
        }).eq("day_id", day_id).execute()
        
        logger.info(f"✅ Day {current_day_number} marked as generated")
        
        # Check if all days are complete
        target_days = state["target_days"]
        if current_day_number >= target_days - 1:
            state["is_complete"] = True
            logger.info(f"🎉 All {target_days} days generated!")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to mark day as generated: {e}", exc_info=True)
        state["error"] = f"Failed to mark day as generated: {str(e)}"
        return state
