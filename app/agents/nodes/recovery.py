"""
Recovery node to retry concepts with empty content or tasks.
Runs after all days are generated to fill in any missing content.
"""

import logging
import asyncio
from app.agents.state import RoadmapAgentState
from app.core.supabase_client import get_supabase_client
from app.agents.nodes.generate_content import generate_content_and_tasks
from app.agents.nodes.save_to_db import save_concept_content

logger = logging.getLogger(__name__)


async def recover_failed_concepts(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Find and retry concepts that have empty content or tasks.
    
    This node:
    1. Queries database for concepts with empty content or tasks
    2. Retries generating content for each failed concept
    3. Updates the database with new content
    """
    project_id = state["project_id"]
    
    logger.info("🔧 Starting recovery phase: Checking for concepts with missing content...")
    
    supabase = get_supabase_client()
    
    try:
        # Find all days for this project
        days_response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number")
            .eq("project_id", project_id)
            .execute()
        )
        
        if not days_response.data:
            logger.info("✅ No days found, nothing to recover")
            return state
        
        day_ids = [day["day_id"] for day in days_response.data]
        day_map = {day["day_id"]: day["day_number"] for day in days_response.data}
        
        # Find concepts with empty content or tasks
        concepts_to_recover = []
        
        for day_id in day_ids:
            # Get concepts for this day
            concepts_response = (
                supabase.table("concepts")
                .select("concept_id, title, description, order_index, content")
                .eq("day_id", day_id)
                .execute()
            )
            
            for concept_data in concepts_response.data:
                concept_id = concept_data["concept_id"]
                concept_title = concept_data["title"]
                content = concept_data.get("content") or ""
                
                # Check tasks count
                tasks_response = (
                    supabase.table("tasks")
                    .select("task_id")
                    .eq("concept_id", concept_id)
                    .execute()
                )
                task_count = len(tasks_response.data or [])
                
                # If content is empty or no tasks, mark for recovery
                if not content.strip() or task_count == 0:
                    concepts_to_recover.append({
                        "concept_id": concept_id,
                        "title": concept_title,
                        "description": concept_data.get("description", ""),
                        "order_index": concept_data["order_index"],
                        "day_id": day_id,
                        "day_number": day_map[day_id],
                        "has_content": bool(content.strip()),
                        "task_count": task_count,
                    })
                    logger.info(
                        f"   Found concept needing recovery: '{concept_title}' "
                        f"(Day {day_map[day_id]}, has_content: {bool(content.strip())}, tasks: {task_count})"
                    )
        
        if not concepts_to_recover:
            logger.info("✅ No concepts need recovery - all have content")
            return state
        
        logger.info(f"🔄 Recovering {len(concepts_to_recover)} concepts...")
        
        # Retry generating content for each concept
        for concept_info in concepts_to_recover:
            concept_id = concept_info["concept_id"]
            concept_title = concept_info["title"]
            day_id = concept_info["day_id"]
            day_number = concept_info["day_number"]
            
            logger.info(f"🔄 Retrying concept: '{concept_title}' (Day {day_number})")
            
            try:
                # Create concept structure for generation
                concept = {
                    "order_index": concept_info["order_index"],
                    "title": concept_title,
                    "description": concept_info.get("description", ""),
                    "content": "",
                    "estimated_minutes": 15,
                    "tasks": [],
                }
                
                # Update state for generation
                state["current_concepts"] = [concept]
                state["current_concept_index"] = 0
                state["current_day_id"] = day_id
                state["current_day_number"] = day_number
                
                # Store concept_id mapping for save_concept_content
                state["concept_ids_map"] = {concept_info["order_index"]: concept_id}
                
                # Generate content
                await generate_content_and_tasks(state)
                
                # Save the generated content
                save_concept_content(state)
                
                logger.info(f"✅ Successfully recovered concept: '{concept_title}'")
                
                # Add delay between concepts to avoid rate limits
                await asyncio.sleep(3)
                
            except Exception as e:
                logger.error(f"❌ Failed to recover concept '{concept_title}': {e}", exc_info=True)
                continue
        
        logger.info(f"✅ Recovery phase completed: {len(concepts_to_recover)} concepts processed")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Recovery phase failed: {e}", exc_info=True)
        return state
