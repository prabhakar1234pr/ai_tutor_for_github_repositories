"""
Agent state definition for roadmap generation.
This defines all the data that flows through the LangGraph nodes.
"""

from typing import TypedDict, List, Optional, Literal, Dict

class RepoAnalysis(TypedDict):
    """Structured analysis of the GitHub repository"""
    summary: str                      # High-level overview of the project
    primary_language: str             # Main programming language
    frameworks: List[str]             # Frameworks/libraries used
    architecture_patterns: List[str]  # MVC, REST API, Microservices, Layered, etc
    difficulty: str                   # Overall complexity assessment

class DayTheme(TypedDict):
    """Theme for a single day in the curriculum"""
    day_number: int
    theme: str
    description: str

class SubConceptData(TypedDict):
    """A single subconcept with markdown content"""
    order_index: int
    title: str
    content: str  # Markdown formatted learning content

class TaskData(TypedDict):
    """A single task for users to complete"""
    order_index: int
    title: str
    description: str
    # Matches database constraint exactly
    task_type: Literal[
        "coding",           # Write code (primary type)
        "reading",          # Read documentation
        "research",         # Research a topic
        "quiz",             # Answer questions
        "github_profile",   # Day 0: Paste GitHub profile
        "create_repo",      # Day 0: Create repository
        "verify_commit"     # Day 0: Make first commit
    ]

class ConceptData(TypedDict):
    """A major learning concept with subconcepts and tasks"""
    order_index: int
    title: str
    description: str
    subconcepts: List[SubConceptData]
    tasks: List[TaskData]

class RoadmapAgentState(TypedDict):
    """
    Complete state for the roadmap generation agent.
    This state is passed between all LangGraph nodes.
    """
    # ===== INPUT (Immutable) =====
    project_id: str           # UUID of the project
    github_url: str           # GitHub repo URL
    skill_level: str          # beginner/intermediate/advanced
    target_days: int          # How many days of learning (e.g., 14)
    
    # ===== ANALYSIS RESULTS =====
    repo_analysis: Optional[RepoAnalysis]  # Structured repo analysis from RAG
    
    # ===== CURRICULUM (Generated once upfront) =====
    curriculum: List[DayTheme]    # All day themes generated at start
    
    # ===== CURRENT GENERATION CONTEXT =====
    current_day_number: int       # Which day we're generating (0, 1, 2...)
    current_day_id: Optional[str] # UUID of current day in database
    current_concepts: List[ConceptData]  # Concepts being generated
    current_concept_index: int    # Which concept we're on
    
    # ===== INTERNAL STATE (Database IDs) =====
    day_ids_map: Optional[Dict[int, str]]  # Mapping day_number -> day_id
    concept_ids_map: Optional[Dict[int, str]]  # Mapping concept order_index -> concept_id
    
    # ===== STATUS TRACKING =====
    is_complete: bool             # Is entire roadmap done?
    error: Optional[str]          # Error message if something failed