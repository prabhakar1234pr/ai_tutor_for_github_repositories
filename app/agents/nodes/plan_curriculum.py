"""
Plan curriculum by generating all day themes upfront.
This ensures consistency across all days.
"""

import logging
from app.agents.state import RoadmapAgentState, DayTheme
from app.services.groq_service import get_groq_service
from app.agents.prompts import CURRICULUM_PLANNING_PROMPT
from app.utils.json_parser import parse_llm_json_response_async

logger = logging.getLogger(__name__)


async def plan_and_save_curriculum(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate all day themes upfront for the entire curriculum.
    
    This node:
    1. Calls Groq LLM to generate themes for all days (1 to target_days)
    2. Parses JSON response into list of DayTheme
    3. Stores curriculum in state
    
    Args:
        state: Current agent state (must have repo_analysis)
        
    Returns:
        Updated state with curriculum populated
    """
    project_id = state["project_id"]
    github_url = state["github_url"]
    skill_level = state["skill_level"]
    target_days = state["target_days"]
    repo_analysis = state.get("repo_analysis")
    
    if not repo_analysis:
        raise ValueError("repo_analysis must be populated before planning curriculum")
    
    logger.info(f"📚 Planning curriculum for {target_days} days...")
    
    # Format repo analysis as string for prompt
    repo_analysis_str = f"""
    Summary: {repo_analysis['summary']}
    Primary Language: {repo_analysis['primary_language']}
    Frameworks: {', '.join(repo_analysis['frameworks'])}
    Architecture Patterns: {', '.join(repo_analysis['architecture_patterns'])}
    Difficulty: {repo_analysis['difficulty']}
    """
    
    # Calculate last day number (Day 0 is fixed, so days 1 to target_days-1)
    last_day_number = target_days - 1  # If target_days=14, we generate days 1-13
    
    # Format the prompt
    prompt = CURRICULUM_PLANNING_PROMPT.format(
        target_days=target_days,
        repo_analysis=repo_analysis_str,
        skill_level=skill_level,
        github_url=github_url,
        last_day_number=last_day_number,
    )
    
    # Call Groq LLM
    groq_service = get_groq_service()
    system_prompt = (
        "You are an expert curriculum designer. "
        "Return ONLY valid JSON array, no markdown, no extra text."
    )
    
    try:
        logger.info(f"🤖 Generating curriculum themes with LLM...")
        # Use async version with rate limiting
        llm_response = await groq_service.generate_response_async(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",  # Context already in prompt
        )
        
        logger.debug(f"   LLM response length: {len(llm_response)} chars")
        
        # Parse JSON response using async parser (supports sanitizer)
        try:
            themes_list = await parse_llm_json_response_async(llm_response, expected_type="array")
        except Exception as parse_error:
            logger.error(f"❌ Failed to parse JSON response: {parse_error}")
            logger.debug(f"   Response text: {llm_response[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {parse_error}")
        
        # Validate and convert to DayTheme objects
        curriculum: list[DayTheme] = []
        
        for i, theme_dict in enumerate(themes_list):
            if not isinstance(theme_dict, dict):
                logger.warning(f"⚠️  Skipping invalid theme at index {i}: not a dict")
                continue
            
            day_theme: DayTheme = {
                "day_number": theme_dict.get("day_number", i + 1),
                "theme": theme_dict.get("theme", ""),
                "description": theme_dict.get("description", ""),
            }
            
            # Validate
            if not day_theme["theme"]:
                logger.warning(f"⚠️  Skipping theme at index {i}: missing theme")
                continue
            
            curriculum.append(day_theme)
        
        # Verify we got the right number of days
        expected_days = last_day_number  # Days 1 to target_days-1
        if len(curriculum) < expected_days:
            logger.warning(
                f"⚠️  Expected {expected_days} days, got {len(curriculum)}. "
                f"Some days may be missing."
            )
        
        logger.info(f"✅ Curriculum planned: {len(curriculum)} days")
        for theme in curriculum[:5]:  # Log first 5
            logger.info(f"   Day {theme['day_number']}: {theme['theme']}")
        if len(curriculum) > 5:
            logger.info(f"   ... and {len(curriculum) - 5} more days")
        
        # Update state
        state["curriculum"] = curriculum
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Curriculum planning failed: {e}", exc_info=True)
        state["error"] = f"Curriculum planning failed: {str(e)}"
        return state

