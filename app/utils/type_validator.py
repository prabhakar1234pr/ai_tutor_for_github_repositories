"""
Type validation utilities for ensuring data structures match expected schemas.
Prevents TypeError and other runtime errors.
"""

import logging
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)


def validate_subconcept(item: Any, index: int = 0) -> Optional[Dict]:
    """
    Validate and normalize a subconcept item.
    
    Args:
        item: The item to validate (could be dict, int, or other)
        index: Index for error reporting
        
    Returns:
        Validated dict or None if invalid
    """
    # Type check
    if not isinstance(item, dict):
        logger.warning(f"⚠️  Skipping subconcept at index {index}: not a dict (got {type(item).__name__})")
        return None
    
    # Required fields check
    required_fields = ["order_index", "title", "content"]
    missing = [f for f in required_fields if f not in item]
    if missing:
        logger.warning(f"⚠️  Skipping subconcept at index {index}: missing fields {missing}")
        return None
    
    # Type validation and normalization
    try:
        validated = {
            "order_index": int(item.get("order_index", index + 1)),
            "title": str(item.get("title", "")).strip(),
            "content": str(item.get("content", "")).strip(),
        }
        
        # Validate non-empty
        if not validated["title"]:
            logger.warning(f"⚠️  Skipping subconcept at index {index}: empty title")
            return None
        
        return validated
        
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️  Skipping subconcept at index {index}: validation error - {e}")
        return None


def validate_task(item: Any, index: int = 0) -> Optional[Dict]:
    """
    Validate and normalize a task item.
    
    Args:
        item: The item to validate (could be dict, int, or other)
        index: Index for error reporting
        
    Returns:
        Validated dict or None if invalid
    """
    # Type check
    if not isinstance(item, dict):
        logger.warning(f"⚠️  Skipping task at index {index}: not a dict (got {type(item).__name__})")
        return None
    
    # Required fields check
    required_fields = ["order_index", "title", "description", "task_type"]
    missing = [f for f in required_fields if f not in item]
    if missing:
        logger.warning(f"⚠️  Skipping task at index {index}: missing fields {missing}")
        return None
    
    # Type validation and normalization
    try:
        validated = {
            "order_index": int(item.get("order_index", index + 1)),
            "title": str(item.get("title", "")).strip(),
            "description": str(item.get("description", "")).strip(),
            "task_type": str(item.get("task_type", "coding")).strip(),
        }
        
        # Validate non-empty
        if not validated["title"]:
            logger.warning(f"⚠️  Skipping task at index {index}: empty title")
            return None
        
        # Ensure task_type is valid
        valid_task_types = ["coding", "reading", "research", "quiz", "github_profile", "create_repo", "verify_commit"]
        if validated["task_type"] not in valid_task_types:
            validated["task_type"] = "coding"  # Default fallback
        
        return validated
        
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️  Skipping task at index {index}: validation error - {e}")
        return None


def validate_and_normalize_subconcepts(subconcepts: Any) -> List[Dict]:
    """
    Validate and normalize a list of subconcepts.
    
    Args:
        subconcepts: Could be list, dict, or other type
        
    Returns:
        List of validated subconcept dicts
    """
    if not isinstance(subconcepts, list):
        logger.warning(f"⚠️  Expected list of subconcepts, got {type(subconcepts).__name__}")
        return []
    
    validated = []
    for idx, item in enumerate(subconcepts):
        validated_item = validate_subconcept(item, index=idx)
        if validated_item:
            validated.append(validated_item)
    
    return validated


def validate_and_normalize_tasks(tasks: Any) -> List[Dict]:
    """
    Validate and normalize a list of tasks.
    
    Args:
        tasks: Could be list, dict, or other type
        
    Returns:
        List of validated task dicts
    """
    if not isinstance(tasks, list):
        logger.warning(f"⚠️  Expected list of tasks, got {type(tasks).__name__}")
        return []
    
    validated = []
    for idx, item in enumerate(tasks):
        validated_item = validate_task(item, index=idx)
        if validated_item:
            validated.append(validated_item)
    
    return validated


def validate_concept(concept: Any) -> Optional[Dict]:
    """
    Validate a concept structure.
    
    Args:
        concept: Concept dict to validate
        
    Returns:
        Validated concept dict or None if invalid
    """
    if not isinstance(concept, dict):
        logger.warning(f"⚠️  Concept is not a dict: {type(concept).__name__}")
        return None
    
    # Ensure subconcepts and tasks are lists
    concept = dict(concept)  # Make a copy
    
    # Validate and normalize subconcepts
    if "subconcepts" in concept:
        concept["subconcepts"] = validate_and_normalize_subconcepts(concept["subconcepts"])
    else:
        concept["subconcepts"] = []
    
    # Validate and normalize tasks
    if "tasks" in concept:
        concept["tasks"] = validate_and_normalize_tasks(concept["tasks"])
    else:
        concept["tasks"] = []
    
    return concept

