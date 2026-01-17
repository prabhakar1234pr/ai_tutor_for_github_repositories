"""
Memory context building node.
Builds context from state-based memory ledger (no database queries).

Optimized for the new curriculum structure:
- Uses memory_ledger from state instead of database queries
- Uses concept_summaries from state for summary text
- References completed concepts, skills unlocked, files touched
"""

import logging

from app.agents.state import RoadmapAgentState

logger = logging.getLogger(__name__)

# Configuration
MAX_COMPLETED_CONCEPTS_IN_CONTEXT = 5  # Last N concepts to include in context


def build_memory_context(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Build memory context from state-based memory ledger.

    This node builds context from in-memory state instead of database queries,
    making it faster and more consistent with the current generation flow.

    Uses:
    - state.memory_ledger: Structured memory with completed_concepts, files_touched, skills_unlocked
    - state.concept_summaries: Map of concept_id -> summary text
    - state.curriculum: For concept titles and metadata

    Args:
        state: Current agent state

    Returns:
        Updated state with memory_context field populated
    """
    memory_ledger = state.get("memory_ledger", {})
    concept_summaries = state.get("concept_summaries", {})
    curriculum = state.get("curriculum", {})

    logger.info("🧠 Building memory context from state ledger...")

    # Get structured data from memory ledger
    completed_concepts = memory_ledger.get("completed_concepts", [])
    files_touched = memory_ledger.get("files_touched", [])
    skills_unlocked = memory_ledger.get("skills_unlocked", [])

    # If no completed concepts, no memory context needed
    if not completed_concepts:
        logger.info("   No completed concepts yet, skipping memory context")
        state["memory_context"] = None
        return state

    # Get concept metadata from curriculum
    concepts_dict = curriculum.get("concepts", {}) if isinstance(curriculum, dict) else {}

    # Build memory context
    memory_parts = []

    # Section 1: Recent Completed Concepts (last N)
    recent_concepts = completed_concepts[-MAX_COMPLETED_CONCEPTS_IN_CONTEXT:]

    if recent_concepts:
        memory_parts.append("=== Recently Completed Concepts ===")

        for concept_id in recent_concepts:
            concept_meta = concepts_dict.get(concept_id, {})
            title = concept_meta.get("title", concept_id)
            summary = concept_summaries.get(concept_id, "")

            memory_parts.append(f"\n**{title}**")
            if summary:
                memory_parts.append(f"{summary}")
            elif concept_meta.get("objective"):
                memory_parts.append(f"Objective: {concept_meta['objective']}")

        memory_parts.append("")

    # Section 2: Skills Unlocked
    if skills_unlocked:
        memory_parts.append("=== Skills Acquired ===")
        # Deduplicate and limit
        unique_skills = list(dict.fromkeys(skills_unlocked))[-15:]  # Last 15 unique skills
        memory_parts.append(", ".join(unique_skills))
        memory_parts.append("")

    # Section 3: Files Explored
    if files_touched:
        memory_parts.append("=== Files Explored ===")
        # Deduplicate and limit
        unique_files = list(dict.fromkeys(files_touched))[-10:]  # Last 10 unique files
        for file_path in unique_files:
            memory_parts.append(f"- {file_path}")
        memory_parts.append("")

    # Section 4: Learning Progress Summary
    total_completed = len(completed_concepts)
    total_skills = len(set(skills_unlocked))
    total_files = len(set(files_touched))

    memory_parts.append("=== Learning Progress ===")
    memory_parts.append(f"Concepts completed: {total_completed}")
    memory_parts.append(f"Skills acquired: {total_skills}")
    memory_parts.append(f"Files explored: {total_files}")

    # Combine into final memory context string
    memory_context = "\n".join(memory_parts).strip()

    logger.info(f"✅ Memory context built ({len(memory_context)} chars)")
    logger.info(f"   Concepts: {total_completed}, Skills: {total_skills}, Files: {total_files}")

    state["memory_context"] = memory_context

    return state


def build_memory_context_for_concept(
    state: RoadmapAgentState,
    target_concept_id: str,
) -> dict:
    """
    Build structured memory context for a specific concept.

    DEPRECATED: Returns structured dict instead of prose to avoid hallucination drift.
    Use app.agents.utils.memory_context.build_structured_memory_context() instead.

    This function is kept for backward compatibility but delegates to the new implementation.

    Args:
        state: Current agent state
        target_concept_id: The concept being generated

    Returns:
        Structured memory context dict (not prose string)
    """
    from app.agents.utils.memory_context import build_structured_memory_context

    return build_structured_memory_context(state, target_concept_id)


# DEPRECATED: Legacy function for backward compatibility
def _retrieve_vector_context(project_id: str, current_day_number: int) -> str | None:
    """
    DEPRECATED: Vector context retrieval is no longer used.
    Memory context is now built from state-based memory ledger.
    """
    return None
