"""
Judge content and tasks quality using LLM-as-Judge.
Evaluates content quality, task quality, verifiability, and difficulty progression.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.config import settings
from app.services.evaluation.data_collection import get_evaluation_collector
from app.services.evaluation.llm_judge import get_llm_judge

logger = logging.getLogger(__name__)


def should_judge_content(state: RoadmapAgentState) -> bool:
    """
    Determine if content and tasks should be judged.

    Conditional logic:
    - Sample 30% of concepts (to reduce LLM calls)
    - Always judge if previous concept had low score
    - Always judge first concept of the day

    Args:
        state: Current agent state

    Returns:
        True if content should be judged
    """
    if not settings.judge_enabled:
        return False

    current_concept_index = state.get("current_concept_index", 0)

    # Always judge first concept
    if current_concept_index == 0:
        return True

    # Sample 30% of remaining concepts
    import random

    return random.random() < 0.3


async def judge_content_and_tasks(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Judge content and tasks quality using LLM-as-Judge.

    This node runs after content and tasks are generated, before saving to database.
    It evaluates:
    - Content Quality: Clear, accurate, complete
    - Task Quality: Actionable, verifiable, progressive
    - Task Verifiability: Can tasks be verified automatically?
    - Difficulty Progression: Tasks progress from easy to hard

    Args:
        state: Current agent state with current_concepts and current_concept_index

    Returns:
        Updated state (judgment scores stored, but doesn't block workflow)
    """
    if not should_judge_content(state):
        return state

    current_concepts = state.get("current_concepts", [])
    current_concept_index = state.get("current_concept_index", 0)

    if current_concept_index >= len(current_concepts):
        return state

    concept = current_concepts[current_concept_index]
    concept_title = concept.get("title", "")
    content = concept.get("content", "")
    tasks = concept.get("tasks", [])

    if not content and not tasks:
        logger.debug(f"   Skipping judgment for {concept_title} - no content or tasks")
        return state

    logger.info(f"⚖️  Judging content and tasks for: {concept_title}")

    try:
        judge = get_llm_judge()

        judgment = await judge.judge_content_and_tasks(
            concept_title=concept_title, content=content, tasks=tasks
        )

        if judgment:
            logger.info(
                f"   ✅ Content & tasks judged: Overall={judgment['overall_score']:.1f}/10, "
                f"Content={judgment['content_quality_score']:.1f}, "
                f"Tasks={judgment['task_quality_score']:.1f}, "
                f"Verifiable={judgment['task_verifiability_score']:.1f}"
            )

            # Store judgment in state (could be used for feedback)
            # Initialize if None or doesn't exist
            if state.get("concept_judgments") is None:
                state["concept_judgments"] = {}
            state["concept_judgments"][current_concept_index] = judgment

            # Save evaluation data to database for DSPy optimization
            try:
                project_id = state.get("project_id")
                current_day_id = state.get("current_day_id")
                current_day_number = state.get("current_day_number", 0)
                concept_ids_map = state.get("concept_ids_map") or {}
                concept_id = concept_ids_map.get(concept["order_index"])
                repo_analysis = state.get("repo_analysis")
                target_days = state.get("target_days", 0)
                skill_level = state.get("skill_level", "")

                # Determine project complexity
                project_complexity = "Moderate"
                if repo_analysis:
                    complexity_map = {
                        "beginner": "Simple",
                        "intermediate": "Moderate",
                        "advanced": "Complex",
                    }
                    project_complexity = complexity_map.get(
                        repo_analysis.get("difficulty", "intermediate"), "Moderate"
                    )

                if concept_id:
                    collector = get_evaluation_collector()

                    # Save content evaluation
                    content_input_data = {
                        "day_number": current_day_number,
                        "target_days": target_days,
                        "concept_title": concept_title,
                        "concept_description": concept.get("description", ""),
                        "skill_level": skill_level,
                        "project_complexity": project_complexity,
                    }

                    # Extract content quality score from judgment
                    content_scores = {
                        "content_quality_score": judgment.get("content_quality_score", 0),
                        "overall_score": judgment.get("overall_score", 0),
                    }

                    await collector.save_content_evaluation(
                        project_id=project_id,
                        concept_id=concept_id,
                        day_id=current_day_id,
                        day_number=current_day_number,
                        input_data=content_input_data,
                        output_content=content,
                        evaluation_scores=content_scores,
                    )

                    # Save tasks evaluation
                    tasks_input_data = {
                        "day_number": current_day_number,
                        "target_days": target_days,
                        "concept_title": concept_title,
                        "concept_description": concept.get("description", ""),
                        "skill_level": skill_level,
                        "project_complexity": project_complexity,
                    }

                    # Extract task-related scores from judgment
                    tasks_scores = {
                        "task_quality_score": judgment.get("task_quality_score", 0),
                        "task_verifiability_score": judgment.get("task_verifiability_score", 0),
                        "difficulty_progression_score": judgment.get(
                            "difficulty_progression_score", 0
                        ),
                        "overall_score": judgment.get("overall_score", 0),
                    }

                    await collector.save_tasks_evaluation(
                        project_id=project_id,
                        concept_id=concept_id,
                        day_id=current_day_id,
                        day_number=current_day_number,
                        input_data=tasks_input_data,
                        output_tasks=tasks,
                        evaluation_scores=tasks_scores,
                    )
            except Exception as e:
                logger.warning(f"   ⚠️  Failed to save content/tasks evaluation data: {e}")
        else:
            logger.warning("   ⚠️  Content & tasks judgment returned no results")

        return state

    except Exception as e:
        logger.error(f"❌ Content & tasks judgment failed: {e}", exc_info=True)
        # Don't fail the workflow
        return state
