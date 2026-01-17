"""
Judge curriculum quality using LLM-as-Judge.
Evaluates curriculum progression, skill level match, completeness, and coherence.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.config import settings
from app.services.evaluation.llm_judge import get_llm_judge

logger = logging.getLogger(__name__)


async def judge_curriculum(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Judge curriculum quality using LLM-as-Judge.

    This node runs after curriculum is planned, before inserting days to database.
    It evaluates:
    - Progression: Logical flow from basics to advanced
    - Skill level match: Appropriate for target skill level
    - Completeness: Covers all necessary topics
    - Coherence: Themes connect logically

    Args:
        state: Current agent state with curriculum and repo_analysis

    Returns:
        Updated state (judgment scores stored, but doesn't block workflow)
    """
    if not settings.judge_enabled:
        logger.debug("LLM-as-Judge disabled, skipping curriculum judgment")
        return state

    curriculum = state.get("curriculum", [])
    skill_level = state.get("skill_level", "intermediate")
    repo_analysis = state.get("repo_analysis")

    if not curriculum:
        logger.warning("   No curriculum to judge")
        return state

    if not repo_analysis:
        logger.warning("   No repo_analysis found, skipping curriculum judgment")
        return state

    logger.info(f"⚖️  Judging curriculum quality ({len(curriculum)} days)...")

    try:
        judge = get_llm_judge()

        # Build repo summary for context
        repo_summary = (
            f"Primary Language: {repo_analysis['primary_language']}\n"
            f"Frameworks: {', '.join(repo_analysis['frameworks'])}\n"
            f"Architecture: {', '.join(repo_analysis['architecture_patterns'])}\n"
            f"Summary: {repo_analysis['summary']}"
        )

        judgment = await judge.judge_curriculum(
            curriculum=curriculum, skill_level=skill_level, repo_summary=repo_summary
        )

        if judgment:
            logger.info(
                f"   ✅ Curriculum judged: Overall={judgment['overall_score']:.1f}/10, "
                f"Progression={judgment['progression_score']:.1f}, "
                f"Skill Match={judgment['skill_level_match_score']:.1f}"
            )

            # Store judgment in state (optional, for downstream use or logging)
            state["curriculum_judgment"] = judgment
        else:
            logger.warning("   ⚠️  Curriculum judgment returned no results")

        return state

    except Exception as e:
        logger.error(f"❌ Curriculum judgment failed: {e}", exc_info=True)
        # Don't fail the workflow - judgment is helpful but not critical
        return state
