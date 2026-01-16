"""
Agent state definition for roadmap generation.
This defines all the data that flows through the LangGraph nodes.
"""

from typing import Literal, TypedDict


class RepoAnalysis(TypedDict):
    """Structured analysis of the GitHub repository"""

    summary: str
    primary_language: str
    frameworks: list[str]
    architecture_patterns: list[str]
    difficulty: str


class DayTheme(TypedDict):
    """Theme for a single day in the curriculum"""

    day_number: int
    theme: str
    description: str


class TaskData(TypedDict):
    """A single task for users to complete"""

    order_index: int
    title: str
    description: str
    task_type: Literal[
        "coding", "reading", "research", "quiz", "github_profile", "create_repo", "verify_commit"
    ]
    estimated_minutes: int
    difficulty: Literal["easy", "medium", "hard"]


class ConceptData(TypedDict):
    """A major learning concept with content and tasks"""

    order_index: int
    title: str
    description: str
    content: str  # Rich markdown documentation
    estimated_minutes: int
    tasks: list[TaskData]


class RoadmapAgentState(TypedDict):
    """
    Complete state for the roadmap generation agent.
    This state is passed between all LangGraph nodes.
    """

    # ===== INPUT (Immutable) =====
    project_id: str
    github_url: str
    skill_level: str
    target_days: int

    # ===== ANALYSIS RESULTS =====
    repo_analysis: RepoAnalysis | None

    # ===== CURRICULUM (Generated once upfront) =====
    curriculum: list[DayTheme]

    # ===== CURRENT GENERATION CONTEXT =====
    current_day_number: int
    current_day_id: str | None
    current_concepts: list[ConceptData]
    current_concept_index: int

    # ===== INTERNAL STATE (Database IDs) =====
    day_ids_map: dict[int, str] | None
    concept_ids_map: dict[int, str] | None

    # ===== STATUS TRACKING =====
    is_complete: bool
    error: str | None
