"""
Utility functions for the roadmap agent.
Includes validation, state management, and helper functions.
"""

import logging
import time
from typing import Any

from app.agents.state import RoadmapAgentState

logger = logging.getLogger(__name__)


def validate_state(state: RoadmapAgentState, required_fields: list[str]) -> None:
    """
    Validate that required fields exist in state and are not None.

    Args:
        state: Current agent state
        required_fields: List of field names that must be present

    Raises:
        ValueError: If any required field is missing or None
    """
    missing = []
    for field in required_fields:
        if field not in state or state[field] is None:
            missing.append(field)

    if missing:
        raise ValueError(
            f"Missing required state fields: {missing}. Available fields: {list(state.keys())}"
        )


def validate_inputs(
    project_id: str,
    github_url: str,
    skill_level: str,
    target_days: Any,
) -> None:
    """
    Validate input parameters before starting the agent.

    Args:
        project_id: UUID of the project
        github_url: GitHub repository URL
        skill_level: Skill level (beginner/intermediate/advanced)
        target_days: Number of days for the roadmap

    Raises:
        ValueError: If any input is invalid
    """
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id must be a non-empty string")

    if not github_url or not isinstance(github_url, str):
        raise ValueError("github_url must be a non-empty string")

    # Validate GitHub URL format
    if not github_url.startswith(("https://github.com/", "http://github.com/")):
        raise ValueError(
            f"Invalid GitHub URL format: {github_url}. "
            f"Must start with https://github.com/ or http://github.com/"
        )

    if skill_level not in ["beginner", "intermediate", "advanced"]:
        raise ValueError(
            f"Invalid skill_level: {skill_level}. Must be one of: beginner, intermediate, advanced"
        )

    if not isinstance(target_days, int):
        raise ValueError(f"target_days must be an integer, got {type(target_days).__name__}")

    if target_days < 1:
        raise ValueError(f"target_days must be at least 1, got {target_days}")

    if target_days > 100:
        raise ValueError(f"target_days must be at most 100, got {target_days}")


def calculate_recursion_limit(target_days: int, avg_concepts_per_day: int = 4) -> int:
    """
    Calculate recursion limit based on workflow structure.

    Structure:
    - Each day: 1 (select) + 1 (concepts) + N concepts (subconcepts/tasks) + 1 (mark)
    - Recovery: 1 node
    - Note: Day 0 is handled separately via API endpoint, not included here

    Args:
        target_days: Number of days in the roadmap (Days 1-N, Day 0 excluded)
        avg_concepts_per_day: Average number of concepts per day

    Returns:
        Calculated recursion limit with 50% buffer
    """
    per_day_nodes = 1 + 1 + avg_concepts_per_day + 1  # select + concepts + content + mark
    recovery_nodes = 1

    # Calculate base total (only for Days 1-N, Day 0 is handled separately)
    total = (target_days * per_day_nodes) + recovery_nodes

    # Add 50% buffer for retries, errors, and edge cases
    limit = int(total * 1.5)

    # Ensure minimum limit
    min_limit = 50
    if limit < min_limit:
        limit = min_limit

    # Cap at reasonable maximum
    max_limit = 500
    if limit > max_limit:
        limit = max_limit

    logger.info(
        f"📊 Calculated recursion limit: {limit} (target_days={target_days}, avg_concepts={avg_concepts_per_day})"
    )

    return limit


def update_progress(state: RoadmapAgentState, **kwargs) -> RoadmapAgentState:
    """
    Update progress tracking in state.

    Args:
        state: Current agent state
        **kwargs: Progress metrics to update

    Returns:
        Updated state with progress information
    """
    if "progress" not in state or state["progress"] is None:
        state["progress"] = {}

    state["progress"].update(kwargs)
    state["last_updated"] = time.time()

    # Calculate completion percentage if we have current_day_number
    if "current_day_number" in state and "target_days" in state:
        current_day = state.get("current_day_number", 0)
        target_days = state.get("target_days", 0)
        if target_days > 0:
            completion = (current_day / target_days) * 100
            state["progress"]["completion_percentage"] = completion
            state["progress"]["current_day"] = current_day
            state["progress"]["total_days"] = target_days

    return state


def get_error_context(state: RoadmapAgentState) -> dict[str, Any]:
    """
    Get error context from state for better error messages.

    Args:
        state: Current agent state

    Returns:
        Dictionary with error context
    """
    return {
        "project_id": state.get("project_id"),
        "day_number": state.get("current_day_number"),
        "concept_index": state.get("current_concept_index"),
        "concept_title": (
            state.get("current_concepts", [{}])[state.get("current_concept_index", 0)].get(
                "title", "unknown"
            )
            if state.get("current_concepts")
            and state.get("current_concept_index", 0) < len(state.get("current_concepts", []))
            else "unknown"
        ),
        "is_complete": state.get("is_complete", False),
    }


def clean_completed_day_data(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Clean up completed day data from state to save memory.

    Args:
        state: Current agent state

    Returns:
        Updated state with cleaned data
    """
    # Clear concept data for completed day
    if state.get("current_concepts"):
        state["current_concepts"] = []

    # Reset concept index
    state["current_concept_index"] = 0

    # Clear concept_ids_map (keep day_ids_map for reference)
    if state.get("concept_ids_map"):
        state["concept_ids_map"] = {}

    return state
