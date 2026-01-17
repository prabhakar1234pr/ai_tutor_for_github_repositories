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
    1. Are within the window (user_position+1 to user_position+window_size)
    2. Have status "empty" (not yet generated)

    Does NOT include user's current concept - only concepts AFTER it.

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

    # Calculate target position: user + window_size (concepts AFTER user's current)
    start_index = user_current_index + 1
    target_index = min(user_current_index + window_size, len(ordered_concept_ids) - 1)

    # If start_index exceeds target_index, window is empty
    if start_index > target_index:
        return []

    # Get candidates within window (after user's position)
    candidates = ordered_concept_ids[start_index : target_index + 1]

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

    Only generates concepts within the window (user_position+1 to user_position+window_size).
    Does NOT generate concepts after the window - stops when window is full.

    Args:
        ordered_concept_ids: Ordered list of all concept IDs
        concept_status_map: Map of concept_id -> ConceptStatus
        user_current_index: Current index of user in the ordered list
        window_size: How many concepts ahead to generate

    Returns:
        Concept ID to generate within window, or None if window is full/all done
    """
    if not ordered_concept_ids:
        return None

    # Calculate target position: user + window_size (concepts AFTER user's current)
    # If user is at index 0, generate concepts at indices 1, 2 (window_size=2)
    start_index = user_current_index + 1
    target_index = min(user_current_index + window_size, len(ordered_concept_ids) - 1)

    # Only generate concepts within the window (after user's current position)
    for i in range(start_index, target_index + 1):
        concept_id = ordered_concept_ids[i]
        status = concept_status_map.get(concept_id, {}).get("status", "empty")

        if status == "empty":
            return concept_id

    # No empty concepts found within window - window is full
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


def has_generated_up_to_window(
    ordered_concept_ids: list[str],
    concept_status_map: dict[str, "ConceptStatus"],
    user_current_index: int,
    window_size: int = SLIDING_WINDOW_AHEAD,
) -> bool:
    """
    Check if we've generated all concepts up to the sliding window (n+2).

    Returns True if all concepts from user_position+1 to user_position+window_size
    have been generated (have final status). Does NOT include user's current concept.

    Args:
        ordered_concept_ids: Ordered list of all concept IDs
        concept_status_map: Map of concept_id -> ConceptStatus
        user_current_index: Current index of user in the ordered list
        window_size: How many concepts ahead to generate (default: 2)

    Returns:
        True if all concepts in the window (after user's position) are generated, False otherwise
    """
    if not ordered_concept_ids:
        return True

    # Calculate target position: user + window_size (concepts AFTER user's current)
    start_index = user_current_index + 1
    target_index = min(user_current_index + window_size, len(ordered_concept_ids) - 1)

    # If start_index exceeds target_index, window is empty (user is at end)
    if start_index > target_index:
        return True

    # Check if all concepts in the window (after user's position) have final status
    final_statuses = ("ready", "generated_with_errors", "failed")

    for i in range(start_index, target_index + 1):
        concept_id = ordered_concept_ids[i]
        status = concept_status_map.get(concept_id, {}).get("status", "empty")
        if status not in final_statuses:
            return False

    return True
