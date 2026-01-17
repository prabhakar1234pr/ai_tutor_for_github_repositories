"""
Pydantic models for structured LLM output across all nodes.
These models ensure type-safe, validated JSON responses from LLMs.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ===== Content Generation Models =====


class ConceptModel(BaseModel):
    """Model for a learning concept."""

    order_index: int = Field(description="Order of the concept (1-based)")
    title: str = Field(description="Concept title (3-6 words)")
    description: str = Field(description="Brief 1-sentence description of the concept")


class ContentResponseModel(BaseModel):
    """Model for content generation response."""

    content: str = Field(description="Full markdown documentation content")
    estimated_minutes: int = Field(
        description="Estimated time to read and understand this content", ge=5, le=120
    )


class TaskModel(BaseModel):
    """Model for a learning task."""

    order_index: int = Field(description="Order of the task (1-based)")
    title: str = Field(description="Short task title (4-6 words)")
    description: str = Field(description="Detailed instructions for the task")
    task_type: Literal[
        "coding",
        "reading",
        "research",
        "quiz",
        "github_profile",
        "create_repo",
        "verify_commit",
    ] = Field(default="coding", description="Type of task")
    estimated_minutes: int = Field(description="Estimated time to complete the task", ge=5, le=120)
    difficulty: Literal["easy", "medium", "hard"] = Field(
        description="Difficulty level of the task"
    )


# ===== Repository Analysis Model =====


class RepoAnalysisModel(BaseModel):
    """Model for repository analysis response."""

    summary: str = Field(description="Brief summary of the repository")
    primary_language: str = Field(description="Primary programming language used")
    frameworks: list[str] = Field(description="List of frameworks/libraries used")
    architecture_patterns: list[str] = Field(description="List of architecture patterns identified")
    difficulty: Literal["beginner", "intermediate", "advanced"] = Field(
        description="Difficulty level of the project"
    )


# ===== Curriculum Planning Model =====


class DayThemeModel(BaseModel):
    """Model for a day theme in curriculum."""

    day_number: int = Field(description="Day number (1-based)")
    theme: str = Field(description="Theme/topic for the day")
    description: str = Field(description="Brief description of what will be covered")


# ===== Day Summary Model =====


class DaySummaryModel(BaseModel):
    """Model for day summary response."""

    summary_text: str = Field(description="Brief 2-3 sentence summary of the day's learning")
    concepts_list: list[str] = Field(description="List of concept titles covered")
    skills_acquired: list[str] = Field(description="List of skills acquired")
    code_examples_reference: str = Field(
        description="Brief reference to key code patterns or examples"
    )
