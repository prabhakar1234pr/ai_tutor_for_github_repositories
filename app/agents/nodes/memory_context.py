"""
Memory context building node.
Aggregates previous days' summaries to provide continuity in learning.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def build_memory_context(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Build memory context from previous days' summaries.

    This node aggregates summaries from completed days to provide context
    for generating the current day's content. It ensures continuity in the
    learning progression.

    Args:
        state: Current agent state with current_day_number and current_day_id

    Returns:
        Updated state with memory_context field populated
    """
    project_id = state.get("project_id")
    current_day_number = state.get("current_day_number", 0)
    current_day_id = state.get("current_day_id")

    logger.info(f"🧠 Building memory context for Day {current_day_number}")

    # For Day 1, there's no previous context
    if current_day_number <= 1:
        logger.info("   No previous days to aggregate (Day 1 or earlier)")
        state["memory_context"] = None
        return state

    if not current_day_id:
        logger.warning("   current_day_id not found, skipping memory context")
        state["memory_context"] = None
        return state

    try:
        supabase = get_supabase_client()

        # First, get all previous days from roadmap_days
        previous_days_response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number, theme")
            .eq("project_id", project_id)
            .lt("day_number", current_day_number)
            .order("day_number", desc=False)
            .execute()
        )

        if not previous_days_response.data or len(previous_days_response.data) == 0:
            logger.info("   No previous days found")
            state["memory_context"] = None
            return state

        previous_days = previous_days_response.data
        day_ids = [day["day_id"] for day in previous_days]

        # Get summaries for those days
        summaries_response = (
            supabase.table("day_memory_summaries")
            .select(
                "day_id, summary_text, concepts_list, skills_acquired, code_examples_reference, created_at"
            )
            .eq("project_id", project_id)
            .in_("day_id", day_ids)
            .execute()
        )

        if not summaries_response.data or len(summaries_response.data) == 0:
            logger.info("   No previous day summaries found")
            state["memory_context"] = None
            return state

        # Create a map of day_id to summary
        summaries_map = {s["day_id"]: s for s in summaries_response.data}

        # Build structured memory context, ordered by day number
        memory_parts = []

        for day in previous_days:
            day_id = day["day_id"]
            day_number = day["day_number"]
            day_theme = day["theme"]

            summary_data = summaries_map.get(day_id)
            if not summary_data:
                # Skip days without summaries
                continue

            memory_parts.append(f"=== Day {day_number}: {day_theme} ===")
            memory_parts.append(f"Summary: {summary_data.get('summary_text', 'No summary')}")

            concepts = summary_data.get("concepts_list", [])
            if concepts:
                memory_parts.append(f"Concepts Learned: {', '.join(concepts)}")

            skills = summary_data.get("skills_acquired", [])
            if skills:
                memory_parts.append(f"Skills Acquired: {', '.join(skills)}")

            code_examples = summary_data.get("code_examples_reference", "")
            if code_examples:
                memory_parts.append(f"Key Code Patterns: {code_examples}")

            memory_parts.append("")  # Empty line between days

        # Combine into final memory context string
        memory_context = "\n".join(memory_parts).strip()

        # Optionally enhance with vector DB retrieval (if available)
        try:
            vector_context = _retrieve_vector_context(
                project_id=project_id,
                current_day_number=current_day_number,
            )
            if vector_context:
                memory_context = f"{memory_context}\n\n=== Relevant Context from Previous Days ===\n{vector_context}"
        except Exception as e:
            logger.debug(f"   Vector DB retrieval failed (non-critical): {e}")
            # Continue without vector context - database summaries are primary

        logger.info(f"   ✅ Memory context built ({len(memory_context)} chars)")
        state["memory_context"] = memory_context

        return state

    except Exception as e:
        logger.error(f"❌ Failed to build memory context: {e}", exc_info=True)
        # Don't fail the workflow - memory context is helpful but not critical
        state["memory_context"] = None
        return state


def _retrieve_vector_context(project_id: str, current_day_number: int) -> str | None:
    """
    Retrieve relevant context from vector database using semantic search.

    This is a secondary source of memory context. If vector DB is not available
    or fails, the function returns None and the workflow continues with
    database summaries only.

    Args:
        project_id: Project UUID
        current_day_number: Current day number

    Returns:
        Optional string with relevant context, or None if unavailable
    """
    try:
        # Query for relevant concept content from previous days
        # This would require storing concept embeddings in Qdrant
        # For now, return None - this is a placeholder for future enhancement

        # TODO: Implement vector search when concept embeddings are stored
        # Example query structure:
        # results = qdrant.search(
        #     collection_name="concept_embeddings",
        #     query_vector=current_day_theme_embedding,
        #     query_filter=Filter(
        #         must=[
        #             FieldCondition(key="project_id", match=MatchValue(value=project_id)),
        #             FieldCondition(key="day_number", range=Range(lt=current_day_number)),
        #         ]
        #     ),
        #     limit=5
        # )

        return None

    except Exception as e:
        logger.debug(f"Vector DB retrieval skipped: {e}")
        return None
