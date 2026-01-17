"""
Judge concepts quality using LLM-as-Judge.
Evaluates concept appropriateness, progression, clarity, and count.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.config import settings
from app.services.evaluation.data_collection import get_evaluation_collector
from app.services.evaluation.llm_judge import get_llm_judge

logger = logging.getLogger(__name__)


def should_judge_concepts(state: RoadmapAgentState) -> bool:
    """
    Determine if concepts should be judged.

    Conditional logic:
    - Always judge Day 1 (baseline)
    - Judge if day_number > 1 (has previous context)
    - Could add more conditions later (e.g., if previous day had low scores)

    Args:
        state: Current agent state

    Returns:
        True if concepts should be judged
    """
    if not settings.judge_enabled:
        return False

    current_day_number = state.get("current_day_number", 0)

    # Always judge Day 1 (baseline)
    if current_day_number == 1:
        return True

    # Judge if we have previous days (Day 2+)
    if current_day_number > 1:
        return True

    return False


async def judge_concepts(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Judge concepts quality using LLM-as-Judge.

    This node runs after concepts are generated, before saving to database.
    It evaluates:
    - Appropriateness: Concepts match the day theme
    - Progression: Build on previous days
    - Clarity: Titles/descriptions are clear
    - Count: Number of concepts is appropriate

    Args:
        state: Current agent state with current_concepts

    Returns:
        Updated state (judgment scores stored, but doesn't block workflow)
    """
    if not should_judge_concepts(state):
        return state

    current_concepts = state.get("current_concepts", [])
    current_day_number = state.get("current_day_number", 0)
    memory_context = state.get("memory_context")

    if not current_concepts:
        logger.warning("   No concepts to judge")
        return state

    # Get day theme
    from app.core.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    current_day_id = state.get("current_day_id")

    if not current_day_id:
        logger.warning("   current_day_id not found, skipping concept judgment")
        return state

    day_response = (
        supabase.table("roadmap_days").select("theme").eq("day_id", current_day_id).execute()
    )

    if not day_response.data:
        logger.warning("   Day not found, skipping concept judgment")
        return state

    day_theme = day_response.data[0]["theme"]

    logger.info(f"⚖️  Judging {len(current_concepts)} concepts for Day {current_day_number}...")

    try:
        judge = get_llm_judge()

        # Convert concepts to dict format for judge
        concepts_list = [
            {"title": c.get("title", ""), "description": c.get("description", "")}
            for c in current_concepts
        ]

        judgment = await judge.judge_concepts(
            concepts=concepts_list,
            day_number=current_day_number,
            day_theme=day_theme,
            memory_context=memory_context,
        )

        if judgment:
            logger.info(
                f"   ✅ Concepts judged: Overall={judgment['overall_score']:.1f}/10, "
                f"Appropriateness={judgment['appropriateness_score']:.1f}, "
                f"Progression={judgment['progression_score']:.1f}"
            )

            # Store judgment in state
            state["concepts_judgment"] = judgment

            # Save evaluation data to database for DSPy optimization
            try:
                project_id = state.get("project_id")
                repo_analysis = state.get("repo_analysis")
                target_days = state.get("target_days", 0)

                # Build input data (what was passed to the prompt)
                input_data = {
                    "day_number": current_day_number,
                    "day_theme": day_theme,
                    "skill_level": state.get("skill_level", ""),
                    "target_days": target_days,
                    "project_complexity": (
                        repo_analysis.get("difficulty", "intermediate")
                        if repo_analysis
                        else "intermediate"
                    ),
                    "repo_summary": (
                        (
                            f"Primary Language: {repo_analysis.get('primary_language', '')}\n"
                            f"Frameworks: {', '.join(repo_analysis.get('frameworks', []))}\n"
                            f"Architecture: {', '.join(repo_analysis.get('architecture_patterns', []))}\n"
                            f"Summary: {repo_analysis.get('summary', '')}"
                        )
                        if repo_analysis
                        else ""
                    ),
                    "memory_context": memory_context if memory_context else None,
                }

                # Build output data (generated concepts)
                output_concepts = [
                    {
                        "order_index": c.get("order_index", i),
                        "title": c.get("title", ""),
                        "description": c.get("description", ""),
                    }
                    for i, c in enumerate(current_concepts)
                ]

                collector = get_evaluation_collector()
                await collector.save_concepts_evaluation(
                    project_id=project_id,
                    day_id=current_day_id,
                    day_number=current_day_number,
                    input_data=input_data,
                    output_concepts=output_concepts,
                    evaluation_scores=judgment,
                )
            except Exception as e:
                logger.warning(f"   ⚠️  Failed to save concepts evaluation data: {e}")
        else:
            logger.warning("   ⚠️  Concepts judgment returned no results")

        return state

    except Exception as e:
        logger.error(f"❌ Concepts judgment failed: {e}", exc_info=True)
        # Don't fail the workflow
        return state
