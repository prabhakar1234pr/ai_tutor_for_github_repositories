"""
Pydantic models for structured LLM outputs used by roadmap agent nodes.

These models mirror the TypedDict structures in `app/agents/state.py` and the
JSON contracts described in prompts under `app/agents/prompts/`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RepoAnalysisModel(BaseModel):
    summary: str
    primary_language: str
    frameworks: list[str] = Field(default_factory=list)
    architecture_patterns: list[str] = Field(default_factory=list)
    difficulty: str


class DayThemeModel(BaseModel):
    day_number: int
    theme: str
    description: str
    concept_ids: list[str] = Field(default_factory=list)


class ConceptMetadataModel(BaseModel):
    title: str
    objective: str
    repo_anchors: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"]


class CurriculumModel(BaseModel):
    days: list[DayThemeModel]
    concepts: dict[str, ConceptMetadataModel]
    dependency_graph: dict[str, list[str]] = Field(default_factory=dict)


class ConceptBundleModel(BaseModel):
    content: str
    estimated_minutes: int = 15
    summary: str
    skills_unlocked: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)


TaskType = Literal[
    "coding",
    "reading",
    "research",
    "quiz",
    "github_profile",
    "create_repo",
    "verify_commit",
]


Difficulty = Literal["easy", "medium", "hard"]


class TaskModel(BaseModel):
    order_index: int
    title: str
    description: str
    task_type: TaskType = "coding"
    estimated_minutes: int = 15
    difficulty: Difficulty = "medium"

    hints: list[str] = Field(default_factory=list)
    solution: str | None = None


class TasksBundleModel(BaseModel):
    tasks: list[TaskModel] = Field(default_factory=list)


class TaskWithTestModel(BaseModel):
    order_index: int
    title: str
    description: str
    task_type: TaskType = "coding"
    estimated_minutes: int = 15
    difficulty: Difficulty = "medium"

    # Optional extended fields used by task generation + verification
    hints: list[str] = Field(default_factory=list)
    solution: str | None = None
    test_file_path: str | None = None
    test_file_content: str | None = None
    test_command: str | None = None


class TasksWithTestsBundleModel(BaseModel):
    tasks: list[TaskWithTestModel] = Field(default_factory=list)


class GeneratedConceptModel(BaseModel):
    order_index: int
    title: str
    description: str


class ContentOnlyModel(BaseModel):
    content: str
    estimated_minutes: int = 15


class DaySummaryModel(BaseModel):
    summary_text: str
    concepts_list: list[str] = Field(default_factory=list)
    skills_acquired: list[str] = Field(default_factory=list)
    code_examples_reference: str = ""


class VerificationPatternsModel(BaseModel):
    class RequiredFunction(BaseModel):
        name: str
        params: list[str] = Field(default_factory=list)
        return_type: str | None = None

    class RequiredClass(BaseModel):
        name: str
        methods: list[str] = Field(default_factory=list)

    class PatternItem(BaseModel):
        type: str
        pattern: str
        description: str

    required_functions: list[RequiredFunction] = Field(default_factory=list)
    required_classes: list[RequiredClass] = Field(default_factory=list)
    required_imports: list[str] = Field(default_factory=list)
    code_patterns: list[PatternItem] = Field(default_factory=list)
    forbidden_patterns: list[PatternItem] = Field(default_factory=list)


class CurriculumJudgmentModel(BaseModel):
    progression_score: float
    skill_level_match_score: float
    completeness_score: float
    coherence_score: float
    overall_score: float


class ConceptsJudgmentModel(BaseModel):
    appropriateness_score: float
    progression_score: float
    clarity_score: float
    count_score: float
    overall_score: float


class ContentAndTasksJudgmentModel(BaseModel):
    content_quality_score: float
    task_quality_score: float
    task_verifiability_score: float
    difficulty_progression_score: float
    overall_score: float


class DayOverallJudgmentModel(BaseModel):
    coherence_score: float
    completeness_score: float
    time_estimates_score: float
    continuity_score: float
    overall_score: float
