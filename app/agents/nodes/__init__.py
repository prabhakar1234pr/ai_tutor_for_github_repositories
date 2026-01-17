"""
LangGraph node implementations for roadmap generation.

New optimized functions:
- generate_concept_content: Lazy loading with retry and inline summary
- save_all_concepts_to_db: Save ALL concepts from curriculum upfront
- mark_concept_complete: Concept-level completion tracking
- build_memory_context: State-based memory (no DB queries)

Deprecated (kept for backward compatibility):
- select_next_incomplete_day: Use generate_concept_content instead
- generate_concepts_for_day: Concepts now in plan_curriculum
- save_concepts_to_db: Use save_all_concepts_to_db instead
- mark_day_generated: Use mark_concept_complete instead
- create_day_summary: Summaries now inline in generate_concept_content
"""

from app.agents.nodes.analyze_repo import analyze_repository
from app.agents.nodes.day_summary import create_day_summary
from app.agents.nodes.fetch_context import fetch_project_context
from app.agents.nodes.generate_content import (
    # New function
    generate_concept_content,
    # Deprecated functions (kept for backward compatibility)
    generate_concepts_for_day,
    generate_subconcepts_and_tasks,
    select_next_incomplete_day,
)
from app.agents.nodes.memory_context import (
    build_memory_context,
    build_memory_context_for_concept,
)
from app.agents.nodes.plan_curriculum import plan_and_save_curriculum
from app.agents.nodes.save_to_db import (
    insert_all_days_to_db,
    mark_concept_complete,
    # Deprecated functions (kept for backward compatibility)
    mark_day_generated,
    # New functions
    save_all_concepts_to_db,
    save_concept_content,
    save_concepts_to_db,
)

# Note: generate_day0_content and save_day0_content removed - Day 0 handled via API endpoint

__all__ = [
    # Core functions
    "fetch_project_context",
    "analyze_repository",
    "plan_and_save_curriculum",
    "insert_all_days_to_db",
    # New optimized functions
    "save_all_concepts_to_db",
    "build_memory_context",
    "build_memory_context_for_concept",
    "generate_concept_content",
    "mark_concept_complete",
    # Deprecated (backward compatibility)
    "select_next_incomplete_day",
    "generate_concepts_for_day",
    "generate_subconcepts_and_tasks",
    "save_concepts_to_db",
    "save_concept_content",
    "mark_day_generated",
    "create_day_summary",
]
