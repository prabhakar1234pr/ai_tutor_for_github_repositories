"""
Content generation nodes using LLM.
These nodes generate concepts, content, and tasks.
"""

import logging
from app.agents.state import RoadmapAgentState, ConceptData
from app.services.groq_service import get_groq_service
from app.agents.prompts import (
    CONCEPTS_GENERATION_PROMPT,
    CONTENT_GENERATION_PROMPT,
    TASKS_GENERATION_PROMPT,
)
from app.agents.day0 import get_day_0_content
from app.core.supabase_client import get_supabase_client
from app.utils.json_parser import parse_llm_json_response_async
from app.utils.type_validator import (
    validate_and_normalize_tasks,
    validate_concept
)

logger = logging.getLogger(__name__)


def generate_day0_content(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Get Day 0 fixed content and add it to state.
    """
    logger.info("📝 Generating Day 0 content (fixed)...")
    
    _, day0_concepts = get_day_0_content()
    state["_day0_concepts"] = day0_concepts
    
    logger.info(f"✅ Day 0 content prepared ({len(day0_concepts)} concepts)")
    
    return state


def select_next_incomplete_day(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Select the next day that needs content generation.
    """
    project_id = state["project_id"]
    
    logger.info("🔍 Selecting next incomplete day...")
    
    supabase = get_supabase_client()
    
    try:
        response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number, theme")
            .eq("project_id", project_id)
            .eq("generated_status", "pending")
            .order("day_number", desc=False)
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
        
        state["current_day_number"] = day_number
        state["current_day_id"] = day_id
        state["current_concepts"] = []
        state["current_concept_index"] = 0
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to select next day: {e}", exc_info=True)
        state["error"] = f"Failed to select next day: {str(e)}"
        return state


async def generate_concepts_for_day(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate concept titles for the current day.
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
    
    repo_summary = (
        f"Primary Language: {repo_analysis['primary_language']}\n"
        f"Frameworks: {', '.join(repo_analysis['frameworks'])}\n"
        f"Architecture: {', '.join(repo_analysis['architecture_patterns'])}\n"
        f"Summary: {repo_analysis['summary']}"
    )
    
    prompt = CONCEPTS_GENERATION_PROMPT.format(
        day_number=current_day_number,
        day_theme=day_theme,
        day_description=day_description,
        skill_level=skill_level,
        repo_summary=repo_summary,
    )
    
    groq_service = get_groq_service()
    system_prompt = (
        "You are an expert curriculum designer. "
        "Return ONLY valid JSON array, no markdown, no extra text."
    )
    
    try:
        llm_response = await groq_service.generate_response_async(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",
        )
        
        concepts_list = await parse_llm_json_response_async(llm_response, expected_type="array")
        
        # Convert to ConceptData objects
        current_concepts: list[ConceptData] = []
        for concept_dict in concepts_list:
            concept: ConceptData = {
                "order_index": concept_dict.get("order_index", len(current_concepts) + 1),
                "title": concept_dict.get("title", ""),
                "description": concept_dict.get("description", ""),
                "content": "",  # Will be filled later
                "estimated_minutes": 15,  # Will be updated later
                "tasks": [],  # Will be filled later
            }
            current_concepts.append(concept)
        
        logger.info(f"✅ Generated {len(current_concepts)} concepts for Day {current_day_number}")
        for concept in current_concepts:
            logger.info(f"   • {concept['title']}")
        
        state["current_concepts"] = current_concepts
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to generate concepts: {e}", exc_info=True)
        state["error"] = f"Failed to generate concepts: {str(e)}"
        return state


async def generate_content_and_tasks(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate content and tasks for the current concept.
    Processes one concept at a time (the one at current_concept_index).
    """
    current_concepts = state.get("current_concepts", [])
    current_concept_index = state.get("current_concept_index", 0)
    current_day_number = state.get("current_day_number", 0)
    skill_level = state["skill_level"]
    
    if current_concept_index >= len(current_concepts):
        logger.warning("⚠️  No more concepts to process")
        return state
    
    concept = current_concepts[current_concept_index]
    
    logger.info(f"🤖 Generating content and tasks for: {concept['title']}")
    
    groq_service = get_groq_service()
    
    try:
        # Generate content
        content_prompt = CONTENT_GENERATION_PROMPT.format(
            day_number=current_day_number,
            concept_title=concept["title"],
            concept_description=concept.get("description", ""),
            skill_level=skill_level,
        )
        
        logger.debug("   Calling LLM for content...")
        content_response = await groq_service.generate_response_async(
            user_query=content_prompt,
            system_prompt="You are an expert educator. Return ONLY valid JSON object, no markdown.",
            context="",
        )
        
        # Parse content JSON
        try:
            content_data = await parse_llm_json_response_async(content_response, expected_type="object")
            concept["content"] = content_data.get("content", "")
            concept["estimated_minutes"] = content_data.get("estimated_minutes", 15)
            
            # Warn if content is empty after parsing
            if not concept["content"] or concept["content"].strip() == "":
                logger.warning(
                    f"⚠️  Content is empty after parsing for concept '{concept['title']}'. "
                    f"Parsed data keys: {list(content_data.keys())}. "
                    f"Response preview: {content_response[:500]}"
                )
            else:
                logger.debug(f"   Generated content ({len(concept['content'])} chars)")
        except Exception as parse_error:
            logger.warning(f"⚠️  Failed to parse content JSON: {parse_error}")
            logger.debug(f"   Response preview: {content_response[:500]}")
            concept["content"] = ""
            concept["estimated_minutes"] = 15
        
        # Generate tasks
        tasks_prompt = TASKS_GENERATION_PROMPT.format(
            day_number=current_day_number,
            concept_title=concept["title"],
            concept_description=concept.get("description", ""),
            skill_level=skill_level,
        )
        
        logger.debug("   Calling LLM for tasks...")
        tasks_response = await groq_service.generate_response_async(
            user_query=tasks_prompt,
            system_prompt="You are an expert educator. Return ONLY valid JSON array, no markdown.",
            context="",
        )
        
        # Parse and validate tasks JSON
        try:
            tasks_raw = await parse_llm_json_response_async(tasks_response, expected_type="array")
            concept["tasks"] = validate_and_normalize_tasks(tasks_raw)
            logger.debug(f"   Generated {len(concept['tasks'])} valid tasks")
        except Exception as parse_error:
            logger.warning(f"⚠️  Failed to parse tasks JSON: {parse_error}")
            concept["tasks"] = []
        
        logger.info(f"✅ Generated content for concept: {concept['title']}")
        
        state["current_concepts"] = current_concepts
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Failed to generate content/tasks: {e}", exc_info=True)
        concept["content"] = concept.get("content", "")
        concept["tasks"] = concept.get("tasks", [])
        logger.warning(f"⚠️  Using fallback for concept '{concept['title']}'")
        state["current_concepts"] = current_concepts
        return state


# Keep the old function name as an alias for backwards compatibility
generate_subconcepts_and_tasks = generate_content_and_tasks
