"""
Database operations for saving roadmap content.
All nodes that write to Supabase database.
"""

import logging
from typing import Dict, List
from app.agents.state import RoadmapAgentState, DayTheme, ConceptData
from app.core.supabase_client import get_supabase_client
from app.agents.day0 import get_day_0_content
import httpx

logger = logging.getLogger(__name__)

# Import postgrest exception if available
try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except ImportError:
    # Fallback if postgrest is not available
    PostgrestAPIError = Exception


def insert_all_days_to_db(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Insert all day themes into roadmap_days table.
    
    This creates rows for all days (including Day 0) with generated_status='pending'.
    Later nodes will update these rows as content is generated.
    
    Args:
        state: Current agent state (must have curriculum)
        
    Returns:
        Updated state with day_ids stored (we'll store them in a dict)
    """
    project_id = state["project_id"]
    curriculum = state.get("curriculum", [])
    target_days = state["target_days"]
    
    logger.info(f"💾 Inserting {target_days} days into database...")
    
    supabase = get_supabase_client()
    
    # Prepare all days to insert
    days_to_insert = []
    
    # Day 0 (fixed)
    day0_theme, _ = get_day_0_content()
    days_to_insert.append({
        "project_id": project_id,
        "day_number": 0,
        "theme": day0_theme["theme"],
        "description": day0_theme["description"],
        "generated_status": "pending",
    })
    
    # Days 1 to target_days-1 (from curriculum)
    for theme in curriculum:
        days_to_insert.append({
            "project_id": project_id,
            "day_number": theme["day_number"],
            "theme": theme["theme"],
            "description": theme["description"],
            "generated_status": "pending",
        })
    
    # Insert all days
    try:
        response = supabase.table("roadmap_days").insert(days_to_insert).execute()
        
        if not response.data:
            raise ValueError("Failed to insert days into database")
        
        # Store day_ids in state (we'll use a dict mapping day_number -> day_id)
        day_ids_map: Dict[int, str] = {}
        for day_data in response.data:
            day_number = day_data["day_number"]
            day_id = day_data["day_id"]
            day_ids_map[day_number] = day_id
        
        logger.info(f"✅ Inserted {len(response.data)} days into database")
        logger.debug(f"   Day IDs: {list(day_ids_map.keys())}")
        
        # Verify Day 0 is in the map
        if 0 not in day_ids_map:
            logger.error(f"❌ Day 0 not found in inserted days! Day numbers: {sorted(day_ids_map.keys())}")
            raise ValueError("Day 0 was not inserted correctly")
        
        logger.debug(f"   Day 0 ID: {day_ids_map[0]}")
        
        # Store in state
        state["day_ids_map"] = day_ids_map
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to insert days: {e}", exc_info=True)
        state["error"] = f"Failed to insert days: {str(e)}"
        return state


def save_day0_content(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Save Day 0 content (concepts, subconcepts, tasks) to database.
    
    Args:
        state: Current agent state (must have Day 0 content)
        
    Returns:
        Updated state
    """
    project_id = state["project_id"]
    day_ids_map = state.get("day_ids_map") or {}
    day0_id = day_ids_map.get(0) if day_ids_map else None
    
    # Fallback: Query database if day_ids_map is missing
    if not day0_id:
        logger.warning("⚠️  Day 0 ID not found in state, querying database...")
        supabase = get_supabase_client()
        day_response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number")
            .eq("project_id", project_id)
            .eq("day_number", 0)
            .execute()
        )
        
        if day_response.data and len(day_response.data) > 0:
            day0_id = day_response.data[0]["day_id"]
            logger.info(f"✅ Found Day 0 ID from database: {day0_id}")
            # Update state with the found ID
            if not state.get("day_ids_map"):
                state["day_ids_map"] = {}
            state["day_ids_map"][0] = day0_id
        else:
            logger.error(f"❌ Day 0 not found in database for project {project_id}")
            raise ValueError("Day 0 ID not found. Did insert_all_days_to_db run?")
    
    logger.info(f"💾 Saving Day 0 content to database...")
    
    # Get Day 0 content
    _, day0_concepts = get_day_0_content()
    
    supabase = get_supabase_client()
    
    try:
        # Insert concepts
        concepts_to_insert = []
        for concept in day0_concepts:
            concepts_to_insert.append({
                "day_id": day0_id,
                "order_index": concept["order_index"],
                "title": concept["title"],
                "description": concept["description"],
                "generated_status": "generated",  # Day 0 is pre-generated
            })
        
        concepts_response = supabase.table("concepts").insert(concepts_to_insert).execute()
        
        if not concepts_response.data:
            raise ValueError("Failed to insert Day 0 concepts")
        
        logger.info(f"✅ Inserted {len(concepts_response.data)} concepts for Day 0")
        
        # Create mapping: order_index -> concept_id
        concept_ids_map: Dict[int, str] = {}
        for concept_data in concepts_response.data:
            order_idx = concept_data["order_index"]
            concept_id = concept_data["concept_id"]
            concept_ids_map[order_idx] = concept_id
        
        # Insert subconcepts and tasks
        for concept in day0_concepts:
            concept_id = concept_ids_map[concept["order_index"]]
            
            # Insert subconcepts
            if concept.get("subconcepts"):
                subconcepts_to_insert = []
                for subconcept in concept["subconcepts"]:
                    subconcepts_to_insert.append({
                        "concept_id": concept_id,
                        "order_index": subconcept["order_index"],
                        "title": subconcept["title"],
                        "content": subconcept["content"],
                        "generated_status": "generated",
                    })
                
                supabase.table("sub_concepts").insert(subconcepts_to_insert).execute()
                logger.debug(f"   Inserted {len(subconcepts_to_insert)} subconcepts for concept {concept['title']}")
            
            # Insert tasks
            if concept.get("tasks"):
                tasks_to_insert = []
                for task in concept["tasks"]:
                    tasks_to_insert.append({
                        "concept_id": concept_id,
                        "order_index": task["order_index"],
                        "title": task["title"],
                        "description": task["description"],
                        "task_type": task["task_type"],
                        "generated_status": "generated",
                    })
                
                supabase.table("tasks").insert(tasks_to_insert).execute()
                logger.debug(f"   Inserted {len(tasks_to_insert)} tasks for concept {concept['title']}")
        
        # Mark Day 0 as generated
        supabase.table("roadmap_days").update({
            "generated_status": "generated"
        }).eq("day_id", day0_id).execute()
        
        logger.info(f"✅ Day 0 content saved successfully")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to save Day 0 content: {e}", exc_info=True)
        state["error"] = f"Failed to save Day 0 content: {str(e)}"
        return state


def save_concepts_to_db(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Save concept titles to database (before generating subconcepts/tasks).
    
    Args:
        state: Current agent state (must have current_concepts)
        
    Returns:
        Updated state with concept_ids stored
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
        # Insert concepts with generated_status='generating'
        concepts_to_insert = []
        for concept in current_concepts:
            concepts_to_insert.append({
                "day_id": day_id,
                "order_index": concept["order_index"],
                "title": concept["title"],
                "description": concept.get("description", ""),
                "generated_status": "generating",
            })
        
        response = supabase.table("concepts").insert(concepts_to_insert).execute()
        
        if not response.data:
            raise ValueError("Failed to insert concepts")
        
        # Store concept_ids in state (mapping order_index -> concept_id)
        concept_ids_map: Dict[int, str] = {}
        for concept_data in response.data:
            order_idx = concept_data["order_index"]
            concept_id = concept_data["concept_id"]
            concept_ids_map[order_idx] = concept_id
        
        logger.info(f"✅ Inserted {len(response.data)} concepts")
        
        # Update state
        state["concept_ids_map"] = concept_ids_map
        state["current_concept_index"] = 0  # Start from first concept
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to save concepts: {e}", exc_info=True)
        state["error"] = f"Failed to save concepts: {str(e)}"
        return state


def save_concept_content(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Save subconcepts and tasks for the current concept.
    
    Args:
        state: Current agent state (must have current_concepts with content)
        
    Returns:
        Updated state (increments current_concept_index)
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
        # Insert subconcepts
        if concept.get("subconcepts"):
            subconcepts_to_insert = []
            for subconcept in concept["subconcepts"]:
                # Type guard - ensure subconcept is a dict
                if not isinstance(subconcept, dict):
                    logger.warning(f"⚠️  Skipping invalid subconcept (type: {type(subconcept).__name__})")
                    continue
                
                try:
                    subconcepts_to_insert.append({
                        "concept_id": concept_id,
                        "order_index": int(subconcept.get("order_index", 0)),
                        "title": str(subconcept.get("title", "")),
                        "content": str(subconcept.get("content", "")),
                        "generated_status": "generated",
                    })
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"⚠️  Error processing subconcept: {e}, skipping")
                    continue
            
            try:
                supabase.table("sub_concepts").insert(subconcepts_to_insert).execute()
                logger.debug(f"   Inserted {len(subconcepts_to_insert)} subconcepts")
            except PostgrestAPIError as db_error:
                error_msg = str(db_error)
                if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
                    logger.warning(f"⚠️  Duplicate subconcepts detected for concept '{concept['title']}', skipping insert")
                else:
                    raise
            except httpx.HTTPStatusError as http_error:
                if http_error.response.status_code == 429:
                    logger.warning(f"⚠️  Rate limit hit while inserting subconcepts for '{concept['title']}', will retry later")
                    # Mark concept as generating_with_errors and continue
                    supabase.table("concepts").update({
                        "generated_status": "generating_with_errors"
                    }).eq("concept_id", concept_id).execute()
                    state["current_concept_index"] = current_concept_index + 1
                    return state
                else:
                    raise
        
        # Insert tasks
        if concept.get("tasks"):
            tasks_to_insert = []
            for task in concept["tasks"]:
                # Type guard - ensure task is a dict
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
                        "generated_status": "generated",
                    })
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"⚠️  Error processing task: {e}, skipping")
                    continue
            
            try:
                supabase.table("tasks").insert(tasks_to_insert).execute()
                logger.debug(f"   Inserted {len(tasks_to_insert)} tasks")
            except PostgrestAPIError as db_error:
                error_msg = str(db_error)
                if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
                    logger.warning(f"⚠️  Duplicate tasks detected for concept '{concept['title']}', skipping insert")
                else:
                    raise
            except httpx.HTTPStatusError as http_error:
                if http_error.response.status_code == 429:
                    logger.warning(f"⚠️  Rate limit hit while inserting tasks for '{concept['title']}', will retry later")
                    # Mark concept as generating_with_errors and continue
                    supabase.table("concepts").update({
                        "generated_status": "generating_with_errors"
                    }).eq("concept_id", concept_id).execute()
                    state["current_concept_index"] = current_concept_index + 1
                    return state
                else:
                    raise
            except httpx.RemoteProtocolError as protocol_error:
                logger.warning(f"⚠️  Connection error while inserting tasks for '{concept['title']}': {protocol_error}")
                # Mark concept as generating_with_errors and continue
                supabase.table("concepts").update({
                    "generated_status": "generating_with_errors"
                }).eq("concept_id", concept_id).execute()
                state["current_concept_index"] = current_concept_index + 1
                return state
        
        # Mark concept as generated
        supabase.table("concepts").update({
            "generated_status": "generated"
        }).eq("concept_id", concept_id).execute()
        
        logger.info(f"✅ Concept content saved: {concept['title']}")
        
        # Increment concept index
        state["current_concept_index"] = current_concept_index + 1
        
        return state
        
    except (PostgrestAPIError, httpx.HTTPStatusError, httpx.RemoteProtocolError) as e:
        # Handle database/network errors gracefully
        error_msg = str(e)
        if isinstance(e, PostgrestAPIError) and ("duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower()):
            logger.warning(f"⚠️  Duplicate key error for concept '{concept['title']}', marking as generated_with_errors and continuing")
            try:
                supabase.table("concepts").update({
                    "generated_status": "generated_with_errors"
                }).eq("concept_id", concept_id).execute()
            except:
                pass  # If update fails, continue anyway
            state["current_concept_index"] = current_concept_index + 1
            return state
        elif isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
            logger.warning(f"⚠️  Rate limit hit for concept '{concept['title']}', marking as generating_with_errors and continuing")
            try:
                supabase.table("concepts").update({
                    "generated_status": "generating_with_errors"
                }).eq("concept_id", concept_id).execute()
            except:
                pass
            state["current_concept_index"] = current_concept_index + 1
            return state
        else:
            # For other errors, log and continue with partial data
            logger.error(f"❌ Failed to save concept content for '{concept['title']}': {e}", exc_info=True)
            try:
                supabase.table("concepts").update({
                    "generated_status": "generated_with_errors"
                }).eq("concept_id", concept_id).execute()
            except:
                pass
            # Don't set error state - allow graph to continue
            state["current_concept_index"] = current_concept_index + 1
            return state
    except Exception as e:
        # For unexpected errors, log and continue
        logger.error(f"❌ Unexpected error saving concept content for '{concept['title']}': {e}", exc_info=True)
        try:
            supabase.table("concepts").update({
                "generated_status": "generated_with_errors"
            }).eq("concept_id", concept_id).execute()
        except:
            pass
        # Don't set error state - allow graph to continue
        state["current_concept_index"] = current_concept_index + 1
        return state


def mark_day_generated(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Mark the current day as fully generated.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state
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
        if current_day_number >= target_days - 1:  # Days 0 to target_days-1
            state["is_complete"] = True
            logger.info(f"🎉 All {target_days} days generated!")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to mark day as generated: {e}", exc_info=True)
        state["error"] = f"Failed to mark day as generated: {str(e)}"
        return state

