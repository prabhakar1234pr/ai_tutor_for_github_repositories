"""
Agent state definition for roadmap generation.
This defines all the data that flows through the LangGraph nodes.
"""

from typing import TypedDict, List, Optional, Literal, Dict

class RepoAnalysis(TypedDict):
    """Structured analysis of the GitHub repository"""
    summary: str
    primary_language: str
    frameworks: List[str]
    architecture_patterns: List[str]
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
        "coding",
        "reading",
        "research",
        "quiz",
        "github_profile",
        "create_repo",
        "verify_commit"
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
    tasks: List[TaskData]

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
    repo_analysis: Optional[RepoAnalysis]
    
    # ===== CURRICULUM (Generated once upfront) =====
    curriculum: List[DayTheme]
    
    # ===== CURRENT GENERATION CONTEXT =====
    current_day_number: int
    current_day_id: Optional[str]
    current_concepts: List[ConceptData]
    current_concept_index: int
    
    # ===== INTERNAL STATE (Database IDs) =====
    day_ids_map: Optional[Dict[int, str]]
    concept_ids_map: Optional[Dict[int, str]]
    
    # ===== STATUS TRACKING =====
    is_complete: bool
    error: Optional[str]
