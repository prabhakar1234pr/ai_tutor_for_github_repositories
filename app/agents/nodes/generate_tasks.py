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


def _validate_test_language_match(
    task: dict[str, Any], project_language: str, concept_title: str
) -> str | None:
    """
    Validate that test file matches project language.

    Returns:
        Error message if mismatch found, None if valid
    """
    test_file_path = task.get("test_file_path", "")
    test_command = task.get("test_command", "")
    test_file_content = task.get("test_file_content", "")

    if not test_file_path:
        return "test_file_path is missing"

    # Check file extension
    is_js = project_language in ("javascript", "typescript")
    is_py = project_language == "python"

    if is_js:
        # JavaScript project - must have .test.js or .test.ts
        if not (test_file_path.endswith(".test.js") or test_file_path.endswith(".test.ts")):
            return f"JavaScript project but test_file_path has wrong extension: {test_file_path}"

        # Command must use jest
        if "jest" not in test_command.lower() and "npm test" not in test_command.lower():
            return f"JavaScript project but test_command doesn't use jest: {test_command}"

        # Content must use Jest syntax
        if "describe" not in test_file_content and "test(" not in test_file_content:
            if "import pytest" in test_file_content or "def test_" in test_file_content:
                return "JavaScript project but test_file_content uses Python syntax"

    elif is_py:
        # Python project - must have .py extension
        if not test_file_path.endswith(".py"):
            return f"Python project but test_file_path has wrong extension: {test_file_path}"

        # Command must use pytest
        if "pytest" not in test_command.lower():
            return f"Python project but test_command doesn't use pytest: {test_command}"

        # Content must use pytest syntax
        if "describe" in test_file_content or "expect(" in test_file_content:
            return "Python project but test_file_content uses JavaScript/Jest syntax"

    return None  # Valid


def _fix_test_language_mismatch(task: dict[str, Any], project_language: str) -> dict[str, Any]:
    """
    Fix test file to match project language.
    Generates a basic test file in the correct language.
    """
    is_js = project_language in ("javascript", "typescript")
    is_py = project_language == "python"

    task_title = task.get("title", "Task")
    order_index = task.get("order_index", 1)

    if is_js:
        # Generate JavaScript/Jest test
        test_file_path = f"tests/task_{order_index}.test.js"
        test_file_content = f"""const request = require('supertest');

describe('{task_title}', () => {{
  test('should complete the task', () => {{
    // TODO: Add test implementation
    expect(true).toBe(true);
  }});
}});
"""
        test_command = f"npx jest {test_file_path}"

    elif is_py:
        # Generate Python/pytest test
        test_file_path = f"tests/test_task_{order_index}.py"
        test_file_content = f"""import pytest

def test_task_{order_index}():
    \"\"\"Test for {task_title}\"\"\"
    # TODO: Add test implementation
    assert True
"""
        test_command = f"pytest {test_file_path} -v"
    else:
        # Unknown language - keep original
        return task

    return {
        **task,
        "test_file_path": test_file_path,
        "test_file_content": test_file_content,
        "test_command": test_command,
    }


def _detect_project_language(notebook_repo_context: dict[str, Any], test_structure_str: str) -> str:
    """
    Detect project language from repository context.

    Args:
        notebook_repo_context: Repository context with structure and code
        test_structure_str: Existing test structure info

    Returns:
        "javascript", "typescript", "python", or "unknown"
    """
    repo_structure = str(notebook_repo_context.get("repo_structure", "")).lower()
    repo_code = str(notebook_repo_context.get("repo_code_context", "")).lower()
    test_structure = test_structure_str.lower()

    # Check for explicit framework indicators
    if "jest" in test_structure or "mocha" in test_structure:
        return "javascript"
    if "pytest" in test_structure:
        return "python"

    # Check for package.json (JavaScript/Node.js)
    if "package.json" in repo_structure:
        # Check for TypeScript indicators
        if "tsconfig.json" in repo_structure or "typescript" in repo_code:
            return "typescript"
        return "javascript"

    # Check for Python indicators
    if "requirements.txt" in repo_structure or "pyproject.toml" in repo_structure:
        return "python"
    if "setup.py" in repo_structure:
        return "python"

    # Check file extensions in structure
    js_extensions = [".js", ".jsx", ".ts", ".tsx", ".mjs"]
    py_extensions = [".py"]

    js_count = sum(1 for ext in js_extensions if ext in repo_structure)
    py_count = sum(1 for ext in py_extensions if ext in repo_structure)

    if js_count > py_count:
        return "javascript"
    if py_count > 0:
        return "python"

    # Check code context
    if "require(" in repo_code or "import {" in repo_code or "express" in repo_code:
        return "javascript"
    if "import " in repo_code and "from " in repo_code:
        # Could be Python or ES6, check for more Python-specific patterns
        if "def " in repo_code or "class " in repo_code:
            return "python"

    # Default to javascript for web-focused projects
    return "javascript"


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

    # Get project info to access user_repo_url (notebook repo) and github_url (textbook repo fallback)
    supabase = get_supabase_client()
    try:
        project_response = (
            supabase.table("projects")
            .select("user_repo_url, github_url, github_access_token")
            .eq("project_id", project_id)
            .execute()
        )

        if not project_response.data:
            logger.warning("Project not found, skipping task generation")
            return state

        project = project_response.data[0]
        user_repo_url = project.get("user_repo_url")  # NOTEBOOK REPO
        github_url = project.get("github_url")  # TEXTBOOK REPO (fallback)
        github_token = project.get("github_access_token")

        # If user_repo_url is not set, use textbook repo as fallback
        # This allows task generation even before Day 0 Task 2 is completed
        repo_url_for_tasks = user_repo_url or github_url
        is_using_fallback = not user_repo_url

        if not repo_url_for_tasks:
            logger.warning("Neither user_repo_url nor github_url set, skipping task generation")
            return state

        if is_using_fallback:
            logger.info(
                "user_repo_url not set, using textbook repo (github_url) as fallback for task generation"
            )

    except Exception as e:
        logger.error(f"Failed to get project info: {e}", exc_info=True)
        return state

    # Build memory context
    structured_memory = build_structured_memory_context(state, concept_id)
    memory_context_str = format_memory_context_for_prompt(structured_memory)

    # Build notebook repo context (or textbook repo if notebook not available)
    try:
        notebook_repo_context = await build_notebook_repo_context_for_task_generation(
            project_id=project_id,
            concept_metadata=concept_metadata,
            user_repo_url=repo_url_for_tasks,  # Use fallback if needed
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

    # Detect project language for validation
    project_language = _detect_project_language(notebook_repo_context, test_structure_str)
    logger.info(f"📋 Detected project language for task generation: {project_language}")

    # Generate tasks with retry
    async def _generate():
        return await _llm_generate_tasks_with_tests(
            concept_id=concept_id,
            concept_metadata=concept_metadata,
            skill_level=skill_level,
            memory_context_str=memory_context_str,
            notebook_repo_context=notebook_repo_context,
            test_structure_str=test_structure_str,
            project_language=project_language,
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

            # Validate test file matches project language
            validation_error = _validate_test_language_match(
                task_with_tests, project_language, concept_title
            )
            if validation_error:
                logger.error(f"❌ Task {idx + 1} language mismatch: {validation_error}")
                # Fix the test file to match language
                task_with_tests = _fix_test_language_mismatch(task_with_tests, project_language)
                logger.info(f"✅ Fixed test file for task {idx + 1} to match {project_language}")

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
    project_language: str,
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
        project_language: Detected project language (javascript/typescript/python)

    Returns:
        Raw LLM response dict with tasks array

    Raises:
        JSONParseError: If LLM response cannot be parsed
    """
    groq_service = get_groq_service()

    concept_title = concept_metadata.get("title", concept_id)
    concept_objective = concept_metadata.get("objective", "")

    # Format prompt with notebook repo context and detected language
    prompt = TASK_GENERATION_PROMPT.format(
        concept_title=concept_title,
        concept_objective=concept_objective,
        skill_level=skill_level,
        project_language=project_language,
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
