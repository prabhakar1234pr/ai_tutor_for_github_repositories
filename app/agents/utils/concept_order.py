"""
Utility functions for deriving concept order and generation window.

These functions compute the ordered list of concepts and generation candidates
from the curriculum structure, avoiding the need to store a generation_queue in state.

This eliminates state synchronization issues and makes the system more resilient.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.state import ConceptStatus

# Configuration for lazy loading
SLIDING_WINDOW_AHEAD = 2  # Generate N concepts ahead of user position


def get_ordered_concept_ids(curriculum: dict) -> list[str]:
    """
    Derive the ordered list of all concept IDs from curriculum.

    Order is determined by:
    1. Day order (day_number ascending)
    2. Within each day, concept_ids list order

    Args:
        curriculum: Curriculum structure with days and concepts

    Returns:
        Ordered list of concept IDs
    """
    if not isinstance(curriculum, dict):
        return []

    days_list = curriculum.get("days", [])
    if not days_list:
        return []

    # Sort days by day_number
    sorted_days = sorted(days_list, key=lambda d: d.get("day_number", 0))

    # Extract concept IDs in order
    ordered_concept_ids = []
    for day in sorted_days:
        concept_ids = day.get("concept_ids", [])
        ordered_concept_ids.extend(concept_ids)

    return ordered_concept_ids


def get_user_current_index(
    ordered_concept_ids: list[str],
    user_current_concept_id: str | None,
) -> int:
    """
    Get the index of the user's current concept in the ordered list.

    Args:
        ordered_concept_ids: Ordered list of all concept IDs
        user_current_concept_id: Current concept ID user is on (or None)

    Returns:
        Index of user's current concept, or 0 if not found/None
    """
    if not user_current_concept_id:
        return 0

    try:
        return ordered_concept_ids.index(user_current_concept_id)
    except ValueError:
        # Concept not found in list, default to start
        return 0


def compute_generation_window(
    ordered_concept_ids: list[str],
    concept_status_map: dict[str, "ConceptStatus"],
    user_current_index: int,
    window_size: int = SLIDING_WINDOW_AHEAD,
) -> list[str]:
    """
    Compute which concepts should be generated based on sliding window.

    Returns concepts that:
    1. Are within the window (user_position to user_position + window_size)
    2. Have status "empty" (not yet generated)

    Args:
        ordered_concept_ids: Ordered list of all concept IDs
        concept_status_map: Map of concept_id -> ConceptStatus
        user_current_index: Current index of user in the ordered list
        window_size: How many concepts ahead to generate (default: 2)

    Returns:
        List of concept IDs that should be generated (in order)
    """
    if not ordered_concept_ids:
        return []

    # Calculate target position (user + window)
    target_index = min(user_current_index + window_size, len(ordered_concept_ids) - 1)

    # Get candidates within window
    candidates = ordered_concept_ids[user_current_index : target_index + 1]

    # Filter to only "empty" concepts
    generation_candidates = [
        cid for cid in candidates if concept_status_map.get(cid, {}).get("status") == "empty"
    ]

    return generation_candidates


def select_next_concept_to_generate(
    ordered_concept_ids: list[str],
    concept_status_map: dict[str, "ConceptStatus"],
    user_current_index: int,
    window_size: int = SLIDING_WINDOW_AHEAD,
) -> str | None:
    """
    Select the next concept to generate based on sliding window.

    Priority:
    1. First "empty" concept within window (user_position to user_position + window_size)
    2. If all in window are done, first "empty" concept after window
    3. If all are done, return None

    Args:
        ordered_concept_ids: Ordered list of all concept IDs
        concept_status_map: Map of concept_id -> ConceptStatus
        user_current_index: Current index of user in the ordered list
        window_size: How many concepts ahead to generate

    Returns:
        Concept ID to generate, or None if all are done
    """
    if not ordered_concept_ids:
        return None

    # Calculate target position (user + window)
    target_index = min(user_current_index + window_size, len(ordered_concept_ids) - 1)

    # First, try to find empty concept within window
    for i in range(user_current_index, target_index + 1):
        concept_id = ordered_concept_ids[i]
        status = concept_status_map.get(concept_id, {}).get("status", "empty")

        if status == "empty":
            return concept_id

    # If all in window are done, try to find any empty concept after window
    for i in range(target_index + 1, len(ordered_concept_ids)):
        concept_id = ordered_concept_ids[i]
        status = concept_status_map.get(concept_id, {}).get("status", "empty")

        if status == "empty":
            return concept_id

    # No empty concepts found
    return None


def are_all_concepts_complete(
    ordered_concept_ids: list[str],
    concept_status_map: dict[str, "ConceptStatus"],
) -> bool:
    """
    Check if all concepts have been generated (have final status).

    Args:
        ordered_concept_ids: Ordered list of all concept IDs
        concept_status_map: Map of concept_id -> ConceptStatus

    Returns:
        True if all concepts have final status, False otherwise
    """
    if not ordered_concept_ids:
        return True

    final_statuses = ("ready", "generated_with_errors", "failed")

    return all(
        concept_status_map.get(cid, {}).get("status") in final_statuses
        for cid in ordered_concept_ids
    )
