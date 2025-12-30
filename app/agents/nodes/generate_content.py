"""
Content generation nodes using LLM.
These nodes generate concepts, subconcepts, and tasks.
"""

import logging
import json
from app.agents.state import RoadmapAgentState, ConceptData
from app.services.groq_service import get_groq_service
from app.agents.prompts import (
    CONCEPTS_GENERATION_PROMPT,
    SUBCONCEPTS_GENERATION_PROMPT,
    TASKS_GENERATION_PROMPT,
)
from app.agents.day0 import get_day_0_content
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def generate_day0_content(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Get Day 0 fixed content and add it to state.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with Day 0 content
    """
    logger.info("📝 Generating Day 0 content (fixed)...")
    
    # Get Day 0 content
    _, day0_concepts = get_day_0_content()
    
    # Store in state (we'll use this in save_day0_content)
    state["_day0_concepts"] = day0_concepts
    
    logger.info(f"✅ Day 0 content prepared ({len(day0_concepts)} concepts)")
    
    return state


def select_next_incomplete_day(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Select the next day that needs content generation.
    
    This queries the database for the next day with generated_status='pending'.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with current_day_number and current_day_id set
    """
    project_id = state["project_id"]
    day_ids_map = state.get("day_ids_map") or {}
    
    logger.info("🔍 Selecting next incomplete day...")
    
    supabase = get_supabase_client()
    
    try:
        # Find next day with generated_status='pending'
        response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number, theme")
            .eq("project_id", project_id)
            .eq("generated_status", "pending")
            .order("day_number", desc=False)  # Ascending order
            .limit(1)
            .execute()
        )
        
        if not response.data or len(response.data) == 0:
            logger.info("✅ No more days to generate")
            state["is_complete"] = True
            return state
        
        day_data = response.data[0]
        day_id = day_data["day_id"]
        day_number = day_data["day_number"]
        theme = day_data["theme"]
        
        logger.info(f"📅 Selected Day {day_number}: {theme}")
        
        # Update state
        state["current_day_number"] = day_number
        state["current_day_id"] = day_id
        state["current_concepts"] = []
        state["current_concept_index"] = 0
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to select next day: {e}", exc_info=True)
        state["error"] = f"Failed to select next day: {str(e)}"
        return state


def generate_concepts_for_day(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate concept titles for the current day.
    
    Args:
        state: Current agent state (must have current_day_number and repo_analysis)
        
    Returns:
        Updated state with current_concepts populated (titles only, no subconcepts/tasks yet)
    """
    current_day_number = state.get("current_day_number")
    current_day_id = state.get("current_day_id")
    repo_analysis = state.get("repo_analysis")
    skill_level = state["skill_level"]
    
    if not current_day_id:
        raise ValueError("current_day_id not found. Did select_next_incomplete_day run?")
    
    if not repo_analysis:
        raise ValueError("repo_analysis not found. Did analyze_repository run?")
    
    # Get day theme from database
    supabase = get_supabase_client()
    day_response = (
        supabase.table("roadmap_days")
        .select("theme, description")
        .eq("day_id", current_day_id)
        .execute()
    )
    
    if not day_response.data:
        raise ValueError(f"Day {current_day_number} not found in database")
    
    day_data = day_response.data[0]
    day_theme = day_data["theme"]
    day_description = day_data.get("description", "")
    
    logger.info(f"🤖 Generating concepts for Day {current_day_number}: {day_theme}")
    
    # Format repo summary
    repo_summary = (
        f"Primary Language: {repo_analysis['primary_language']}\n"
        f"Frameworks: {', '.join(repo_analysis['frameworks'])}\n"
        f"Architecture: {', '.join(repo_analysis['architecture_patterns'])}\n"
        f"Summary: {repo_analysis['summary']}"
    )
    
    # Format prompt
    prompt = CONCEPTS_GENERATION_PROMPT.format(
        day_number=current_day_number,
        day_theme=day_theme,
        day_description=day_description,
        skill_level=skill_level,
        repo_summary=repo_summary,
    )
    
    # Call Groq LLM
    groq_service = get_groq_service()
    system_prompt = (
        "You are an expert curriculum designer. "
        "Return ONLY valid JSON array, no markdown, no extra text."
    )
    
    try:
        llm_response = groq_service.generate_response(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",
        )
        
        # Parse JSON
        response_text = llm_response.strip()
        if response_text.startswith("```"):
            start_idx = response_text.find("```") + 3
            if response_text[start_idx:start_idx+5] == "json":
                start_idx += 5
            end_idx = response_text.rfind("```")
            response_text = response_text[start_idx:end_idx].strip()
        
        concepts_list = json.loads(response_text)
        
        # Convert to ConceptData objects (without subconcepts/tasks yet)
        current_concepts: list[ConceptData] = []
        for concept_dict in concepts_list:
            concept: ConceptData = {
                "order_index": concept_dict.get("order_index", len(current_concepts) + 1),
                "title": concept_dict.get("title", ""),
                "description": concept_dict.get("description", ""),
                "subconcepts": [],  # Will be filled later
                "tasks": [],  # Will be filled later
            }
            current_concepts.append(concept)
        
        logger.info(f"✅ Generated {len(current_concepts)} concepts for Day {current_day_number}")
        for concept in current_concepts:
            logger.info(f"   • {concept['title']}")
        
        # Update state
        state["current_concepts"] = current_concepts
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to generate concepts: {e}", exc_info=True)
        state["error"] = f"Failed to generate concepts: {str(e)}"
        return state


def generate_subconcepts_and_tasks(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate subconcepts and tasks for the current concept.
    
    This processes one concept at a time (the one at current_concept_index).
    
    Args:
        state: Current agent state (must have current_concepts and current_concept_index)
        
    Returns:
        Updated state with subconcepts and tasks added to current concept
    """
    current_concepts = state.get("current_concepts", [])
    current_concept_index = state.get("current_concept_index", 0)
    current_day_number = state.get("current_day_number", 0)
    repo_analysis = state.get("repo_analysis")
    skill_level = state["skill_level"]
    
    if current_concept_index >= len(current_concepts):
        logger.warning("⚠️  No more concepts to process")
        return state
    
    concept = current_concepts[current_concept_index]
    
    logger.info(f"🤖 Generating subconcepts and tasks for: {concept['title']}")
    
    if not repo_analysis:
        raise ValueError("repo_analysis not found")
    
    groq_service = get_groq_service()
    
    try:
        # Generate subconcepts
        subconcepts_prompt = SUBCONCEPTS_GENERATION_PROMPT.format(
            day_number=current_day_number,
            concept_title=concept["title"],
            concept_description=concept.get("description", ""),
            skill_level=skill_level,
        )
        
        logger.debug("   Calling LLM for subconcepts...")
        subconcepts_response = groq_service.generate_response(
            user_query=subconcepts_prompt,
            system_prompt="You are an expert educator. Return ONLY valid JSON array, no markdown.",
            context="",
        )
        
        # Parse subconcepts JSON
        subconcepts_text = subconcepts_response.strip()
        if subconcepts_text.startswith("```"):
            start_idx = subconcepts_text.find("```") + 3
            if subconcepts_text[start_idx:start_idx+5] == "json":
                start_idx += 5
            end_idx = subconcepts_text.rfind("```")
            subconcepts_text = subconcepts_text[start_idx:end_idx].strip()
        
        subconcepts_list = json.loads(subconcepts_text)
        concept["subconcepts"] = subconcepts_list
        logger.debug(f"   Generated {len(subconcepts_list)} subconcepts")
        
        # Generate tasks
        tasks_prompt = TASKS_GENERATION_PROMPT.format(
            day_number=current_day_number,
            concept_title=concept["title"],
            concept_description=concept.get("description", ""),
            skill_level=skill_level,
        )
        
        logger.debug("   Calling LLM for tasks...")
        tasks_response = groq_service.generate_response(
            user_query=tasks_prompt,
            system_prompt="You are an expert educator. Return ONLY valid JSON array, no markdown.",
            context="",
        )
        
        # Parse tasks JSON
        tasks_text = tasks_response.strip()
        if tasks_text.startswith("```"):
            start_idx = tasks_text.find("```") + 3
            if tasks_text[start_idx:start_idx+5] == "json":
                start_idx += 5
            end_idx = tasks_text.rfind("```")
            tasks_text = tasks_text[start_idx:end_idx].strip()
        
        tasks_list = json.loads(tasks_text)
        # Ensure all tasks have task_type="coding" (unless Day 0)
        for task in tasks_list:
            if "task_type" not in task:
                task["task_type"] = "coding"
        concept["tasks"] = tasks_list
        logger.debug(f"   Generated {len(tasks_list)} tasks")
        
        logger.info(f"✅ Generated content for concept: {concept['title']}")
        
        # Update state
        state["current_concepts"] = current_concepts
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to generate subconcepts/tasks: {e}", exc_info=True)
        state["error"] = f"Failed to generate content for concept: {str(e)}"
        return state

