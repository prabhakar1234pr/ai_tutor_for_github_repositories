"""
Judge day overall quality using LLM-as-Judge.
Evaluates day coherence, completeness, time estimates, and continuity.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.config import settings
from app.services.evaluation.llm_judge import get_llm_judge

logger = logging.getLogger(__name__)


async def judge_day_overall(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Judge entire day's overall quality using LLM-as-Judge.

    This node runs after all concepts are generated, before marking day complete.
    It evaluates:
    - Coherence: All concepts work together
    - Completeness: Day covers the theme fully
    - Time Estimates: Realistic for completion
    - Continuity: Builds on previous days

    Args:
        state: Current agent state with current_day_id and memory_context

    Returns:
        Updated state (judgment scores stored, but doesn't block workflow)
    """
    if not settings.judge_enabled:
        logger.debug("LLM-as-Judge disabled, skipping day overall judgment")
        return state

    project_id = state.get("project_id")
    current_day_id = state.get("current_day_id")
    current_day_number = state.get("current_day_number", 0)
    memory_context = state.get("memory_context")

    if not current_day_id:
        logger.warning("   current_day_id not found, skipping day overall judgment")
        return state

    logger.info(f"⚖️  Judging Day {current_day_number} overall quality...")

    try:
        from app.core.supabase_client import get_supabase_client

        supabase = get_supabase_client()

        # Get day theme
        day_response = (
            supabase.table("roadmap_days").select("theme").eq("day_id", current_day_id).execute()
        )

        if not day_response.data:
            logger.warning("   Day not found, skipping day overall judgment")
            return state

        day_theme = day_response.data[0]["theme"]

        judge = get_llm_judge()

        judgment = await judge.judge_day_overall(
            day_id=current_day_id,
            day_number=current_day_number,
            day_theme=day_theme,
            project_id=project_id,
            memory_context=memory_context,
        )

        if judgment:
            logger.info(
                f"   ✅ Day overall judged: Overall={judgment['overall_score']:.1f}/10, "
                f"Coherence={judgment['coherence_score']:.1f}, "
                f"Completeness={judgment['completeness_score']:.1f}, "
                f"Continuity={judgment['continuity_score']:.1f}"
            )

            # Store judgment in state
            state["day_judgment"] = judgment
        else:
            logger.warning("   ⚠️  Day overall judgment returned no results")

        return state

    except Exception as e:
        logger.error(f"❌ Day overall judgment failed: {e}", exc_info=True)
        # Don't fail the workflow
        return state
