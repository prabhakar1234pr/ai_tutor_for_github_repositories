"""
Task generation node.
Generates tasks with test files using notebook repo context.
"""

import logging
from typing import Any

from app.agents.prompts.task_generation import TASK_GENERATION_PROMPT
from app.agents.state import RoadmapAgentState
from app.agents.utils.memory_context import (
    build_structured_memory_context,
    format_memory_context_for_prompt,
)
from app.agents.utils.repo_context import build_notebook_repo_context_for_task_generation
from app.agents.utils.retry_wrapper import generate_with_retry
from app.core.supabase_client import get_supabase_client
from app.services.groq_service import get_groq_service
from app.utils.json_parser import parse_llm_json_response_async
from app.utils.type_validator import validate_and_normalize_tasks

logger = logging.getLogger(__name__)


async def generate_tasks_with_tests(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate tasks with test files for the concept that was just generated.

    This node:
    1. Gets the last generated concept_id from state
    2. Gets user_repo_url (notebook repo) from project
    3. Builds notebook repository context (structure + code)
    4. Calls LLM to generate tasks + tests matching notebook repo
    5. Validates and saves tasks to database
    6. Updates state

    Key: Uses notebook repo (user_repo_url), NOT textbook repo (github_url).

    Args:
        state: Current agent state

    Returns:
        Updated state with generated tasks
    """
    concept_id = state.get("_last_generated_concept_id")
    if not concept_id:
        logger.debug("No concept was generated, skipping task generation")
        return state

    concept_ids_map = state.get("concept_ids_map", {})
    curriculum = state.get("curriculum", {})
    skill_level = state.get("skill_level", "intermediate")
    project_id = state["project_id"]

    # Get concept metadata
    concepts_dict = curriculum.get("concepts", {}) if isinstance(curriculum, dict) else {}
    concept_metadata = concepts_dict.get(concept_id, {})
    concept_title = concept_metadata.get("title", concept_id)

    logger.info(f"🤖 Generating tasks with tests for concept: {concept_title} ({concept_id})")

    # Get project info to access user_repo_url (notebook repo)
    supabase = get_supabase_client()
    try:
        project_response = (
            supabase.table("projects")
            .select("user_repo_url, github_access_token")
            .eq("project_id", project_id)
            .execute()
        )

        if not project_response.data:
            logger.warning("Project not found, skipping task generation")
            return state

        project = project_response.data[0]
        user_repo_url = project.get("user_repo_url")  # NOTEBOOK REPO
        github_token = project.get("github_access_token")

        if not user_repo_url:
            logger.warning(
                "user_repo_url not set (Day 0 Task 2 not completed), skipping task generation"
            )
            return state

    except Exception as e:
        logger.error(f"Failed to get project info: {e}", exc_info=True)
        return state

    # Build memory context
    structured_memory = build_structured_memory_context(state, concept_id)
    memory_context_str = format_memory_context_for_prompt(structured_memory)

    # Build notebook repo context (NOT textbook repo)
    try:
        notebook_repo_context = await build_notebook_repo_context_for_task_generation(
            project_id=project_id,
            concept_metadata=concept_metadata,
            user_repo_url=user_repo_url,
            github_token=github_token,
        )
    except Exception as e:
        logger.error(f"Failed to build notebook repo context: {e}", exc_info=True)
        # Continue with minimal context
        notebook_repo_context = {
            "repo_structure": "Error fetching structure",
            "repo_code_context": "",
            "existing_test_structure": {
                "framework": "none",
                "test_directories": [],
                "config_files": [],
                "test_command": None,
                "has_test_setup": False,
            },
        }

    # Format existing test structure for prompt
    test_structure = notebook_repo_context.get("existing_test_structure", {})
    test_structure_str = (
        f"Framework: {test_structure.get('framework', 'none')}\n"
        f"Test directories: {', '.join(test_structure.get('test_directories', []))}\n"
        f"Test command: {test_structure.get('test_command', 'Not set')}\n"
        f"Config files: {', '.join(test_structure.get('config_files', []))}\n"
        f"Has test setup: {test_structure.get('has_test_setup', False)}"
    )

    # Generate tasks with retry
    async def _generate():
        return await _llm_generate_tasks_with_tests(
            concept_id=concept_id,
            concept_metadata=concept_metadata,
            skill_level=skill_level,
            memory_context_str=memory_context_str,
            notebook_repo_context=notebook_repo_context,
            test_structure_str=test_structure_str,
        )

    result, status_info = await generate_with_retry(
        generate_func=_generate,
        concept_id=concept_id,
        concept_title=concept_title,
    )

    if result:
        # Get raw tasks from LLM
        tasks_raw = result.get("tasks", [])

        # Validate basic task fields (title, description, etc.)
        tasks_validated = validate_and_normalize_tasks(tasks_raw)

        # Merge test file fields from raw tasks back into validated tasks
        # (validate_and_normalize_tasks doesn't preserve test_file_* fields)
        tasks_with_tests = []
        for idx, validated_task in enumerate(tasks_validated):
            raw_task = (
                tasks_raw[idx] if idx < len(tasks_raw) and isinstance(tasks_raw[idx], dict) else {}
            )
            # Merge validated fields with test file fields from raw task
            task_with_tests = {
                **validated_task,
                "test_file_path": raw_task.get("test_file_path"),
                "test_file_content": raw_task.get("test_file_content"),
                "test_command": raw_task.get("test_command"),
            }
            tasks_with_tests.append(task_with_tests)

        # Save tasks to database
        database_concept_id = concept_ids_map.get(concept_id)
        if database_concept_id and tasks_with_tests:
            await _save_tasks_to_db(database_concept_id, tasks_with_tests)
            logger.info(
                f"✅ Generated and saved {len(tasks_with_tests)} tasks for concept: {concept_title}"
            )
        else:
            logger.warning(f"No database concept_id found for {concept_id}, tasks not saved")
    else:
        logger.error(f"❌ Failed to generate tasks for concept: {concept_title}")

    return state


async def _llm_generate_tasks_with_tests(
    concept_id: str,
    concept_metadata: dict[str, Any],
    skill_level: str,
    memory_context_str: str,
    notebook_repo_context: dict[str, Any],
    test_structure_str: str,
) -> dict[str, Any]:
    """
    Call LLM to generate tasks with test files.

    Args:
        concept_id: Concept ID
        concept_metadata: Concept metadata from curriculum
        skill_level: User's skill level
        memory_context_str: Formatted memory context string
        notebook_repo_context: Notebook repository context
        test_structure_str: Formatted test structure string

    Returns:
        Raw LLM response dict with tasks array

    Raises:
        JSONParseError: If LLM response cannot be parsed
    """
    groq_service = get_groq_service()

    concept_title = concept_metadata.get("title", concept_id)
    concept_objective = concept_metadata.get("objective", "")

    # Format prompt with notebook repo context
    prompt = TASK_GENERATION_PROMPT.format(
        concept_title=concept_title,
        concept_objective=concept_objective,
        skill_level=skill_level,
        notebook_repo_structure=notebook_repo_context.get("repo_structure", ""),
        notebook_repo_code_context=notebook_repo_context.get("repo_code_context", ""),
        existing_test_structure=test_structure_str,
        memory_context=memory_context_str or "No previous learning context.",
    )

    logger.debug(f"   Calling LLM for '{concept_title}' (tasks + tests)...")

    response = await groq_service.generate_response_async(
        user_query=prompt,
        system_prompt="You are an expert technical educator. Return ONLY valid JSON object, no markdown or extra text.",
        context="",
    )

    # Parse the response
    result_data = await parse_llm_json_response_async(response, expected_type="object")

    logger.debug(f"   ✅ LLM response parsed for '{concept_title}'")

    return result_data


async def _save_tasks_to_db(
    database_concept_id: str,
    tasks: list[dict[str, Any]],
) -> None:
    """
    Save generated tasks with test files to database.

    Args:
        database_concept_id: Database concept ID
        tasks: List of task dicts with test file information
    """
    from app.core.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    try:
        tasks_to_insert = []
        for task in tasks:
            if isinstance(task, dict):
                tasks_to_insert.append(
                    {
                        "concept_id": database_concept_id,
                        "order_index": int(task.get("order_index", 0)),
                        "title": str(task.get("title", "")),
                        "description": str(task.get("description", "")),
                        "task_type": str(task.get("task_type", "coding")),
                        "estimated_minutes": int(task.get("estimated_minutes", 15)),
                        "difficulty": str(task.get("difficulty", "medium")),
                        "hints": task.get("hints", []),
                        "solution": task.get("solution"),
                        "test_file_path": task.get("test_file_path"),
                        "test_file_content": task.get("test_file_content"),
                        "test_command": task.get("test_command"),
                        "verification_type": "test_and_llm",
                        "generated_status": "generated",
                    }
                )

        if tasks_to_insert:
            supabase.table("tasks").insert(tasks_to_insert).execute()
            logger.debug(f"   Saved {len(tasks_to_insert)} tasks to database")

    except Exception as e:
        logger.warning(f"⚠️  Failed to save tasks to database: {e}")
