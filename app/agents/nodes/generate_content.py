"""
Content generation nodes using LLM.
Generates concept content with lazy loading and retry logic.

Optimized for the new curriculum structure:
- generate_concept_content: Generates content, tasks, and summary in a SINGLE LLM call
- Uses retry wrapper for resilient LLM calls
- Updates memory_ledger with skills and files
- Derives generation queue from curriculum (not stored in state)

LLM Call Optimization:
- Before: 3 calls per concept (content, tasks, summary)
- After: 1 call per concept (combined CONCEPT_GENERATION_PROMPT)
- For 56 concepts: 170 calls → 58 calls (66% reduction)
"""

import logging
from typing import Any

from app.agents.prompts import (
    CONCEPT_GENERATION_PROMPT,
    # Deprecated prompts (kept for backward compatibility in deprecated functions)
    CONCEPTS_GENERATION_PROMPT,
    CONTENT_GENERATION_PROMPT,
    TASKS_GENERATION_PROMPT,
)
from app.agents.state import ConceptData, RoadmapAgentState
from app.agents.utils.concept_order import (
    get_ordered_concept_ids,
    get_user_current_index,
    select_next_concept_to_generate,
)
from app.agents.utils.retry_wrapper import JSONParseError, generate_with_retry
from app.core.supabase_client import get_supabase_client
from app.services.groq_service import get_groq_service

# Note: Day 0 is handled separately via API endpoint, not imported here
from app.utils.json_parser import parse_llm_json_response_async
from app.utils.type_validator import validate_and_normalize_tasks

logger = logging.getLogger(__name__)

# Configuration for lazy loading
SLIDING_WINDOW_AHEAD = 2  # Generate N concepts ahead of user position

# Note: generate_day0_content has been removed - Day 0 is now handled via API endpoint


# ============================================
# NEW: Concept-level content generation with lazy loading
# ============================================


async def generate_concept_content(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate content for the next concept in the generation window.

    Implements lazy loading with sliding window:
    - If user position is known, generates concepts up to user_position + SLIDING_WINDOW_AHEAD
    - Otherwise, generates the next concept in order

    This node:
    1. Derives ordered concept list from curriculum
    2. Determines which concept to generate next (using sliding window)
    3. Builds memory context for the concept
    4. Generates content and tasks with retry logic
    5. Updates state: concept_status_map, concept_summaries, memory_ledger

    Args:
        state: Current agent state

    Returns:
        Updated state with generated content
    """
    concept_status_map = state.get("concept_status_map", {})
    concept_ids_map = state.get("concept_ids_map", {})
    curriculum = state.get("curriculum", {})
    skill_level = state.get("skill_level", "intermediate")
    user_current_concept_id = state.get("user_current_concept_id")

    # Derive ordered concept list from curriculum (not stored in state)
    ordered_concept_ids = get_ordered_concept_ids(curriculum)

    if not ordered_concept_ids:
        logger.info("✅ No concepts in curriculum")
        state["is_complete"] = True
        return state

    # Get user's current index
    user_current_index = get_user_current_index(ordered_concept_ids, user_current_concept_id)

    # Determine which concept to generate
    concept_id = select_next_concept_to_generate(
        ordered_concept_ids=ordered_concept_ids,
        concept_status_map=concept_status_map,
        user_current_index=user_current_index,
    )

    if not concept_id:
        logger.info("✅ All concepts are generated or being generated")
        # Check if truly complete
        from app.agents.utils.concept_order import are_all_concepts_complete

        if are_all_concepts_complete(ordered_concept_ids, concept_status_map):
            state["is_complete"] = True
        return state

    # Get concept metadata
    concepts_dict = curriculum.get("concepts", {}) if isinstance(curriculum, dict) else {}
    concept_metadata = concepts_dict.get(concept_id, {})
    concept_title = concept_metadata.get("title", concept_id)

    logger.info(f"🤖 Generating content for concept: {concept_title} ({concept_id})")

    # Track the concept that was just generated (for mark_concept_complete)
    # This is different from user_current_concept_id which represents user's position
    state["_last_generated_concept_id"] = concept_id

    # Mark as generating
    concept_status_map[concept_id] = {
        "status": "generating",
        "attempt_count": 0,
        "failure_reason": None,
    }
    state["concept_status_map"] = concept_status_map
    # Note: Do NOT update user_current_concept_id here - it represents the user's position,
    # not the concept being generated. Updating it would shift the window incorrectly.

    # Build structured memory context for this concept
    from app.agents.utils.memory_context import (
        build_structured_memory_context,
        format_memory_context_for_prompt,
    )

    structured_memory = build_structured_memory_context(state, concept_id)
    memory_context_str = format_memory_context_for_prompt(structured_memory)

    # Generate content with retry
    async def _generate():
        return await _llm_generate_concept_bundle(
            concept_id=concept_id,
            concept_metadata=concept_metadata,
            skill_level=skill_level,
            memory_context_str=memory_context_str,
        )

    result, status_info = await generate_with_retry(
        generate_func=_generate,
        concept_id=concept_id,
        concept_title=concept_title,
    )

    # Update status based on result
    concept_status_map[concept_id] = {
        "status": status_info["content_status"],
        "attempt_count": status_info["attempt_count"],
        "failure_reason": status_info.get("failure_reason"),
    }
    state["concept_status_map"] = concept_status_map

    # Ensure _last_generated_concept_id is still set (in case state was reset)
    state["_last_generated_concept_id"] = concept_id

    if result:
        # Validate output before persisting
        validated_result = _validate_concept_output(result, concept_title, concept_metadata)

        # Persist to database
        database_concept_id = concept_ids_map.get(concept_id)
        if database_concept_id:
            # Update project_id in summary save
            await _persist_concept_content(
                database_concept_id=database_concept_id,
                validated_result=validated_result,
                project_id=state["project_id"],
            )

        # Update state and ledger
        _update_concept_ledger(
            state=state,
            concept_id=concept_id,
            validated_result=validated_result,
        )

        logger.info(f"✅ Generated content for concept: {concept_title}")
    else:
        logger.error(f"❌ Failed to generate content for concept: {concept_title}")

    return state


# NOTE: _select_next_concept_to_generate has been REMOVED
# Use select_next_concept_to_generate from app.agents.utils.concept_order instead
# This function derives the queue from curriculum instead of using stored state


# ============================================
# Internal functions for generate_concept_content
# Split into: llm → validate → persist → update_ledger
# ============================================


async def _llm_generate_concept_bundle(
    concept_id: str,
    concept_metadata: dict[str, Any],
    skill_level: str,
    memory_context_str: str,
) -> dict[str, Any]:
    """
    Generate content, tasks, and summary for a single concept in ONE LLM call.

    This is the optimized version that combines what was previously 3 separate
    LLM calls (content, tasks, summary) into a single call.

    Args:
        concept_id: Concept ID
        concept_metadata: Metadata from curriculum
        skill_level: User's skill level
        memory_context: Context from previous concepts

    Returns:
        Dict with content, tasks, estimated_minutes, summary, skills_unlocked, files_touched

    Raises:
        JSONParseError: If LLM response cannot be parsed
    """
    """
    Call LLM to generate concept bundle (content + tasks + summary).

    This is the only function that calls the LLM. All other operations
    (validation, persistence, ledger updates) are separate.

    Args:
        concept_id: Concept ID
        concept_metadata: Concept metadata from curriculum
        skill_level: User's skill level
        memory_context_str: Formatted memory context string

    Returns:
        Raw LLM response dict (not yet validated)

    Raises:
        JSONParseError: If LLM response cannot be parsed
    """
    groq_service = get_groq_service()

    concept_title = concept_metadata.get("title", concept_id)
    concept_objective = concept_metadata.get("objective", "")
    repo_anchors = concept_metadata.get("repo_anchors", [])

    # Format repo anchors for prompt
    repo_anchors_str = ", ".join(repo_anchors) if repo_anchors else "None specified"

    # Single combined prompt for content + tasks + summary
    combined_prompt = CONCEPT_GENERATION_PROMPT.format(
        concept_title=concept_title,
        concept_objective=concept_objective,
        repo_anchors=repo_anchors_str,
        skill_level=skill_level,
        memory_context=memory_context_str,
    )

    logger.debug(
        f"   Calling LLM for '{concept_title}' (single call for content + tasks + summary)..."
    )
    response = await groq_service.generate_response_async(
        user_query=combined_prompt,
        system_prompt="You are an expert technical educator. Return ONLY valid JSON object, no markdown or extra text.",
        context="",
    )

    # Parse the combined response
    result_data = await parse_llm_json_response_async(response, expected_type="object")

    logger.debug(f"   ✅ LLM response parsed for '{concept_title}'")

    return result_data


def _validate_concept_output(
    raw_result: dict[str, Any],
    concept_title: str,
    concept_metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate and normalize LLM output before persisting.

    Args:
        raw_result: Raw LLM response dict
        concept_title: Concept title for error messages
        concept_metadata: Concept metadata (for defaults)

    Returns:
        Validated and normalized result dict

    Raises:
        JSONParseError: If validation fails
    """
    # Extract and validate content
    content = raw_result.get("content", "")
    if not content or not content.strip():
        raise JSONParseError(f"Empty content generated for {concept_title}")

    # Extract and validate tasks
    tasks_raw = raw_result.get("tasks", [])
    tasks = validate_and_normalize_tasks(tasks_raw)

    # Extract other fields with defaults
    estimated_minutes = raw_result.get("estimated_minutes", 15)
    summary = raw_result.get("summary", f"Learned about {concept_title}.")
    skills_unlocked = raw_result.get("skills_unlocked", [])
    files_touched = raw_result.get("files_touched", concept_metadata.get("repo_anchors", []))

    logger.debug(f"   ✅ Validated output: {len(content)} chars content, {len(tasks)} tasks")

    return {
        "content": content,
        "tasks": tasks,
        "estimated_minutes": estimated_minutes,
        "summary": summary,
        "skills_unlocked": skills_unlocked,
        "files_touched": files_touched,
    }


async def _persist_concept_content(
    database_concept_id: str,
    validated_result: dict[str, Any],
    project_id: str,
) -> None:
    """
    Persist validated concept content to database.

    Args:
        database_concept_id: Database concept ID
        validated_result: Validated result dict from _validate_concept_output
        project_id: Project ID for summary save
    """
    content = validated_result["content"]
    tasks = validated_result["tasks"]
    estimated_minutes = validated_result["estimated_minutes"]

    await _save_concept_content_to_db(
        database_concept_id=database_concept_id,
        content=content,
        tasks=tasks,
        estimated_minutes=estimated_minutes,
    )

    # Save summary to database if supported
    await _save_concept_summary_to_db(
        database_concept_id=database_concept_id,
        project_id=project_id,
        summary_result={
            "summary": validated_result["summary"],
            "skills_unlocked": validated_result["skills_unlocked"],
            "files_touched": validated_result["files_touched"],
        },
    )


def _update_concept_ledger(
    state: RoadmapAgentState,
    concept_id: str,
    validated_result: dict[str, Any],
) -> None:
    """
    Update state with concept summary and memory ledger.

    Args:
        state: Current agent state
        concept_id: Concept ID
        validated_result: Validated result dict
    """
    # Update concept_summaries
    concept_summaries = state.get("concept_summaries", {})
    concept_summaries[concept_id] = validated_result["summary"]
    state["concept_summaries"] = concept_summaries

    # Update memory_ledger
    _update_memory_ledger(
        state=state,
        concept_id=concept_id,
        skills_unlocked=validated_result["skills_unlocked"],
        files_touched=validated_result["files_touched"],
    )


# NOTE: _generate_concept_summary_inline has been REMOVED
# Summary generation is now integrated into _generate_content_and_tasks_for_concept
# using the combined CONCEPT_GENERATION_PROMPT (single LLM call)


def _update_memory_ledger(
    state: RoadmapAgentState,
    concept_id: str,
    skills_unlocked: list[str],
    files_touched: list[str],
) -> None:
    """
    Update the memory ledger with completed concept info.

    Merges new data avoiding duplicates.
    """
    memory_ledger = state.get(
        "memory_ledger",
        {
            "completed_concepts": [],
            "files_touched": [],
            "skills_unlocked": [],
        },
    )

    # Add concept to completed list
    if concept_id not in memory_ledger["completed_concepts"]:
        memory_ledger["completed_concepts"].append(concept_id)

    # Merge skills (avoid duplicates)
    existing_skills = set(memory_ledger.get("skills_unlocked", []))
    for skill in skills_unlocked:
        if skill and skill not in existing_skills:
            memory_ledger["skills_unlocked"].append(skill)
            existing_skills.add(skill)

    # Merge files (avoid duplicates)
    existing_files = set(memory_ledger.get("files_touched", []))
    for file_path in files_touched:
        if file_path and file_path not in existing_files:
            memory_ledger["files_touched"].append(file_path)
            existing_files.add(file_path)

    state["memory_ledger"] = memory_ledger


async def _save_concept_content_to_db(
    database_concept_id: str,
    content: str,
    tasks: list[dict],
    estimated_minutes: int,
) -> None:
    """Save generated content to database."""
    from app.utils.markdown_sanitizer import sanitize_markdown_content

    supabase = get_supabase_client()

    try:
        # Sanitize content
        clean_content = sanitize_markdown_content(content)

        # Update concept
        supabase.table("concepts").update(
            {
                "content": clean_content,
                "estimated_minutes": estimated_minutes,
                "generated_status": "generating",  # Will be set to 'generated' by mark_concept_complete
            }
        ).eq("concept_id", database_concept_id).execute()

        # Insert tasks
        if tasks:
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
                            "generated_status": "generated",
                        }
                    )

            if tasks_to_insert:
                supabase.table("tasks").insert(tasks_to_insert).execute()
                logger.debug(f"   Saved {len(tasks_to_insert)} tasks to database")

    except Exception as e:
        logger.warning(f"⚠️  Failed to save content to database: {e}")


async def _save_concept_summary_to_db(
    database_concept_id: str,
    project_id: str,
    summary_result: dict[str, Any],
) -> None:
    """Save concept summary to database (concept_summaries table)."""
    supabase = get_supabase_client()

    try:
        # Try to insert into concept_summaries table
        summary_data = {
            "concept_id": database_concept_id,
            "project_id": project_id,
            "summary_text": summary_result.get("summary", ""),
            "skills_unlocked": summary_result.get("skills_unlocked", []),
            "files_touched": summary_result.get("files_touched", []),
        }

        supabase.table("concept_summaries").upsert(
            summary_data,
            on_conflict="concept_id",
        ).execute()

        logger.debug("   Saved summary to concept_summaries table")

    except Exception as e:
        # Table might not exist in older schema - that's okay
        logger.debug(f"   Could not save to concept_summaries: {e}")


# ============================================
# DEPRECATED: Old day-based generation functions
# ============================================


# DEPRECATED: Use generate_concept_content instead
def select_next_incomplete_day(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    DEPRECATED: Select the next day that needs content generation.

    This function is deprecated. Use generate_concept_content with
    concept-level tracking instead of day-based generation.
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


# DEPRECATED: Concepts are now generated upfront in plan_curriculum
async def generate_concepts_for_day(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    DEPRECATED: Generate concept titles for the current day.

    This function is deprecated. Concepts are now generated upfront
    in plan_and_save_curriculum and saved via save_all_concepts_to_db.
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

    # Build memory context section
    memory_context = state.get("memory_context")
    if memory_context:
        memory_context_section = f"**Previous Days' Learning Context:**\n{memory_context}\n"
    else:
        memory_context_section = (
            "**Previous Days' Learning Context:**\nNo previous days completed yet.\n"
        )

    prompt = CONCEPTS_GENERATION_PROMPT.format(
        day_number=current_day_number,
        day_theme=day_theme,
        day_description=day_description,
        skill_level=skill_level,
        repo_summary=repo_summary,
        memory_context_section=memory_context_section,
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
            content_data = await parse_llm_json_response_async(
                content_response, expected_type="object"
            )
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
