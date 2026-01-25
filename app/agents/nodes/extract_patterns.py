"""
Pattern extraction node.
Extracts verification patterns from test files using LLM.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.core.supabase_client import get_supabase_client
from app.services.pattern_extractor import PatternExtractor

logger = logging.getLogger(__name__)


async def extract_patterns_from_tests(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Extract verification patterns from test files using LLM.

    This node:
    1. Gets tasks that were just generated
    2. For each task with test file, extracts patterns using LLM
    3. Updates tasks in database with patterns
    4. Updates state

    Runs after generate_tasks.

    Args:
        state: Current agent state

    Returns:
        Updated state
    """
    concept_id = state.get("_last_generated_concept_id")
    if not concept_id:
        logger.debug("No concept was generated, skipping pattern extraction")
        return state

    concept_ids_map = state.get("concept_ids_map", {})
    database_concept_id = concept_ids_map.get(concept_id)

    if not database_concept_id:
        logger.warning(
            f"No database concept_id found for {concept_id}, skipping pattern extraction"
        )
        return state

    logger.info(f"🔍 Extracting patterns from test files for concept: {concept_id}")

    # Get tasks for this concept
    supabase = get_supabase_client()
    try:
        tasks_response = (
            supabase.table("tasks")
            .select("task_id, test_file_path, test_file_content")
            .eq("concept_id", database_concept_id)
            .execute()
        )

        if not tasks_response.data:
            logger.debug("No tasks found for concept, skipping pattern extraction")
            return state

        tasks = tasks_response.data
        logger.info(f"Found {len(tasks)} tasks to extract patterns from")

    except Exception as e:
        logger.error(f"Failed to get tasks: {e}", exc_info=True)
        return state

    # Extract patterns for each task with test file
    pattern_extractor = PatternExtractor()
    patterns_extracted = 0

    for task in tasks:
        test_file_content = task.get("test_file_content")
        test_file_path = task.get("test_file_path")

        if not test_file_content or not test_file_path:
            logger.debug(f"Task {task['task_id']} has no test file, skipping pattern extraction")
            continue

        try:
            # Extract patterns from test file
            pattern_result = await pattern_extractor.extract_patterns_from_test(
                test_file_content=test_file_content,
                test_file_path=test_file_path,
                language=None,  # Auto-detect
            )

            if pattern_result["success"]:
                # Update task with patterns
                try:
                    supabase.table("tasks").update(
                        {"verification_patterns": pattern_result["patterns"]}
                    ).eq("task_id", task["task_id"]).execute()

                    patterns_extracted += 1
                    logger.debug(f"✅ Extracted patterns for task: {task['task_id']}")
                except Exception as update_error:
                    # Handle case where updated_at column doesn't exist (database schema issue)
                    error_msg = str(update_error)
                    if "updated_at" in error_msg.lower():
                        logger.warning(
                            f"⚠️ Database schema issue: updated_at column missing in tasks table. "
                            f"Patterns extracted but not saved for task {task['task_id']}. "
                            f"Please add updated_at column to tasks table."
                        )
                    else:
                        logger.error(
                            f"Failed to update task {task['task_id']} with patterns: {update_error}"
                        )
            else:
                logger.warning(
                    f"⚠️ Pattern extraction failed for task {task['task_id']}: "
                    f"{pattern_result.get('error', 'Unknown error')}"
                )
                # Store empty patterns as fallback
                try:
                    supabase.table("tasks").update({"verification_patterns": {}}).eq(
                        "task_id", task["task_id"]
                    ).execute()
                except Exception as update_error:
                    error_msg = str(update_error)
                    if "updated_at" in error_msg.lower():
                        logger.warning(
                            f"⚠️ Database schema issue: updated_at column missing. "
                            f"Cannot save empty patterns for task {task['task_id']}"
                        )
                    else:
                        logger.error(f"Failed to update task with empty patterns: {update_error}")

        except Exception as e:
            logger.error(
                f"Error extracting patterns for task {task['task_id']}: {e}", exc_info=True
            )
            # Store empty patterns as fallback
            try:
                supabase.table("tasks").update({"verification_patterns": {}}).eq(
                    "task_id", task["task_id"]
                ).execute()
            except Exception as update_error:
                error_msg = str(update_error)
                if "updated_at" in error_msg.lower():
                    logger.warning(
                        f"⚠️ Database schema issue: updated_at column missing in tasks table. "
                        f"Cannot save empty patterns for task {task['task_id']}. "
                        f"Please add updated_at column to tasks table."
                    )
                else:
                    logger.error(f"Failed to update task with empty patterns: {update_error}")

    logger.info(f"✅ Extracted patterns for {patterns_extracted}/{len(tasks)} tasks")

    return state
