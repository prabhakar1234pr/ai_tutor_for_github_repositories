"""
Plan curriculum by generating complete structure upfront.
Generates ALL days and ALL concepts in a single Gemini API call.
This ensures consistency across the entire roadmap.

Uses Gemini (Vertex AI) for curriculum planning.

Output structure:
{
    "days": [...],
    "concepts": {...},
    "dependency_graph": {...}
}
"""

import logging
from typing import Any

from app.agents.prompts import CURRICULUM_PLANNING_PROMPT
from app.agents.state import (
    ConceptMetadata,
    ConceptStatus,
    Curriculum,
    DayTheme,
    RoadmapAgentState,
)
from app.services.gemini_service import get_gemini_service
from app.utils.json_parser import parse_llm_json_response_async

logger = logging.getLogger(__name__)


async def plan_and_save_curriculum(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Generate complete curriculum with all days and concepts upfront.

    This node:
    1. Calls Gemini LLM to generate complete curriculum structure
    2. Parses JSON response into Curriculum TypedDict
    3. Validates concepts and dependencies
    4. Initializes concept_status_map for all concepts
    5. Stores curriculum in state

    Args:
        state: Current agent state (must have repo_analysis)

    Returns:
        Updated state with curriculum and concept_status_map populated
    """
    github_url = state["github_url"]
    skill_level = state["skill_level"]
    target_days = state["target_days"]
    repo_analysis = state.get("repo_analysis")

    if not repo_analysis:
        raise ValueError("repo_analysis must be populated before planning curriculum")

    logger.info(f"📚 Planning complete curriculum for {target_days} days...")

    # Format repo analysis as string for prompt
    repo_analysis_str = f"""
    Summary: {repo_analysis["summary"]}
    Primary Language: {repo_analysis["primary_language"]}
    Frameworks: {", ".join(repo_analysis["frameworks"])}
    Architecture Patterns: {", ".join(repo_analysis["architecture_patterns"])}
    Difficulty: {repo_analysis["difficulty"]}
    """

    # Calculate last day number (Day 0 is handled separately via API endpoint)
    # If target_days=14, we generate days 1-13 (Day 0 is separate, so 14 days total)
    last_day_number = target_days - 1

    # Format the prompt
    prompt = CURRICULUM_PLANNING_PROMPT.format(
        target_days=target_days,
        repo_analysis=repo_analysis_str,
        skill_level=skill_level,
        github_url=github_url,
        last_day_number=last_day_number,
    )

    # Call Gemini LLM for curriculum planning
    logger.info("🤖 Initializing Gemini for curriculum planning...")
    gemini_service = get_gemini_service()
    system_prompt = (
        "You are an expert curriculum designer. "
        "Return ONLY valid JSON object with days, concepts, and dependency_graph. "
        "No markdown, no extra text."
    )

    try:
        logger.info("📚 Generating complete curriculum with Gemini (Vertex AI)...")
        logger.info(f"   📋 Target: {target_days} days, Skill Level: {skill_level}")
        logger.debug("   📤 Sending curriculum planning request to Gemini...")

        # Use async version with rate limiting
        llm_response = await gemini_service.generate_response_async(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",  # Context already in prompt
        )

        logger.info(f"   ✅ Gemini curriculum response received ({len(llm_response)} chars)")
        logger.debug(f"   LLM response length: {len(llm_response)} chars")

        # Parse JSON response using async parser (supports sanitizer)
        try:
            curriculum_dict = await parse_llm_json_response_async(
                llm_response, expected_type="object"
            )
        except Exception as parse_error:
            logger.error(f"❌ Failed to parse JSON response: {parse_error}")
            logger.debug(f"   Response text: {llm_response[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {parse_error}") from parse_error

        # Validate and build curriculum structure
        curriculum = _validate_and_build_curriculum(curriculum_dict, last_day_number)

        # Log summary
        total_concepts = len(curriculum.get("concepts", {}))
        total_days = len(curriculum.get("days", []))

        logger.info("✅ Curriculum planned successfully with Gemini:")
        logger.info(f"   📅 Days: {total_days}")
        logger.info(f"   📚 Concepts: {total_concepts}")
        logger.info("   ✨ Powered by Gemini (Vertex AI)")

        # Log first few days
        for day in curriculum.get("days", [])[:3]:
            logger.info(
                f"   Day {day['day_number']}: {day['theme']} "
                f"({len(day.get('concept_ids', []))} concepts)"
            )
        if total_days > 3:
            logger.info(f"   ... and {total_days - 3} more days")

        # Initialize concept_status_map for all concepts
        concept_status_map: dict[str, ConceptStatus] = {}
        for concept_id in curriculum.get("concepts", {}).keys():
            concept_status_map[concept_id] = {
                "status": "empty",
                "attempt_count": 0,
                "failure_reason": None,
            }

        logger.info(f"   Initialized status tracking for {len(concept_status_map)} concepts")

        # Save curriculum_structure to database for incremental generation
        project_id = state["project_id"]
        from app.core.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        try:
            supabase.table("projects").update({"curriculum_structure": curriculum}).eq(
                "project_id", project_id
            ).execute()
            logger.info("💾 Saved curriculum_structure to database")
        except Exception as e:
            logger.warning(f"⚠️  Failed to save curriculum_structure to DB: {e}")

        # Update state
        state["curriculum"] = curriculum
        state["concept_status_map"] = concept_status_map

        return state

    except Exception as e:
        logger.error(f"❌ Curriculum planning failed: {e}", exc_info=True)
        state["error"] = f"Curriculum planning failed: {str(e)}"
        return state


def _validate_and_build_curriculum(
    curriculum_dict: dict[str, Any], expected_days: int
) -> Curriculum:
    """
    Validate and build Curriculum TypedDict from LLM response.

    Validates:
    - days array exists and has correct structure
    - concepts object exists and all referenced concept_ids exist
    - dependency_graph references valid concept IDs
    - No circular dependencies (basic check)

    Args:
        curriculum_dict: Raw dictionary from LLM response
        expected_days: Expected number of days

    Returns:
        Validated Curriculum TypedDict

    Raises:
        ValueError: If validation fails
    """
    # Extract components
    days_list = curriculum_dict.get("days", [])
    concepts_dict = curriculum_dict.get("concepts", {})
    dependency_graph = curriculum_dict.get("dependency_graph", {})

    if not days_list:
        raise ValueError("Curriculum must have 'days' array")

    if not concepts_dict:
        raise ValueError("Curriculum must have 'concepts' object")

    # Validate days
    validated_days: list[DayTheme] = []
    all_concept_ids_in_days: set[str] = set()

    for i, day_dict in enumerate(days_list):
        if not isinstance(day_dict, dict):
            logger.warning(f"⚠️  Skipping invalid day at index {i}: not a dict")
            continue

        day_number = day_dict.get("day_number", i + 1)
        theme = day_dict.get("theme", "")
        description = day_dict.get("description", "")
        concept_ids = day_dict.get("concept_ids", [])

        if not theme:
            logger.warning(f"⚠️  Day {day_number} missing theme, using placeholder")
            theme = f"Day {day_number} Learning"

        # Ensure concept_ids is a list
        if not isinstance(concept_ids, list):
            concept_ids = []

        day_theme: DayTheme = {
            "day_number": day_number,
            "theme": theme,
            "description": description,
            "concept_ids": concept_ids,
        }

        validated_days.append(day_theme)
        all_concept_ids_in_days.update(concept_ids)

    # Validate concepts
    validated_concepts: dict[str, ConceptMetadata] = {}

    for concept_id, concept_dict in concepts_dict.items():
        if not isinstance(concept_dict, dict):
            logger.warning(f"⚠️  Skipping invalid concept {concept_id}: not a dict")
            continue

        # Validate required fields
        title = concept_dict.get("title", "")
        if not title:
            logger.warning(f"⚠️  Concept {concept_id} missing title, using ID as title")
            title = concept_id

        objective = concept_dict.get("objective", "")
        repo_anchors = concept_dict.get("repo_anchors", [])
        depends_on = concept_dict.get("depends_on", [])
        difficulty = concept_dict.get("difficulty", "medium")

        # Ensure lists
        if not isinstance(repo_anchors, list):
            repo_anchors = []
        if not isinstance(depends_on, list):
            depends_on = []

        # Validate difficulty
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        concept_metadata: ConceptMetadata = {
            "title": title,
            "objective": objective,
            "repo_anchors": repo_anchors,
            "depends_on": depends_on,
            "difficulty": difficulty,
        }

        validated_concepts[concept_id] = concept_metadata

    # Check that all concept_ids in days exist in concepts
    missing_concepts = all_concept_ids_in_days - set(validated_concepts.keys())
    if missing_concepts:
        logger.warning(
            f"⚠️  {len(missing_concepts)} concept IDs referenced in days "
            f"but not defined: {list(missing_concepts)[:5]}"
        )

    # Validate dependency graph
    validated_dependency_graph: dict[str, list[str]] = {}
    all_concept_ids = set(validated_concepts.keys())

    for parent_id, children in dependency_graph.items():
        if parent_id not in all_concept_ids:
            logger.warning(f"⚠️  Dependency graph: parent {parent_id} not in concepts")
            continue

        if not isinstance(children, list):
            children = []

        valid_children = [c for c in children if c in all_concept_ids]
        if len(valid_children) != len(children):
            logger.warning(f"⚠️  Dependency graph: some children of {parent_id} not in concepts")

        validated_dependency_graph[parent_id] = valid_children

    # Check for circular dependencies (basic check)
    if _has_circular_dependency(validated_dependency_graph):
        logger.warning("⚠️  Circular dependency detected in dependency_graph")

    # Verify day count
    if len(validated_days) < expected_days:
        logger.warning(
            f"⚠️  Expected {expected_days} days, got {len(validated_days)}. "
            f"Some days may be missing."
        )

    # Build curriculum
    curriculum: Curriculum = {
        "days": validated_days,
        "concepts": validated_concepts,
        "dependency_graph": validated_dependency_graph,
    }

    return curriculum


def _has_circular_dependency(graph: dict[str, list[str]]) -> bool:
    """
    Check for circular dependencies using DFS.

    Args:
        graph: Dependency graph (parent -> children)

    Returns:
        True if circular dependency exists
    """
    visited = set()
    rec_stack = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)

        for child in graph.get(node, []):
            if child not in visited:
                if dfs(child):
                    return True
            elif child in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node):
                return True

    return False
