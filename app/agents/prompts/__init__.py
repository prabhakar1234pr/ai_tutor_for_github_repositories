"""
Prompt templates for roadmap generation agent.
All prompts are designed to return structured JSON for parsing.

This module provides centralized access to all prompt templates.
Individual prompts are organized in separate files for better maintainability.
"""

# Import all prompts from individual modules
from app.agents.prompts.concepts import CONCEPTS_GENERATION_PROMPT
from app.agents.prompts.content import CONTENT_GENERATION_PROMPT
from app.agents.prompts.curriculum import CURRICULUM_PLANNING_PROMPT
from app.agents.prompts.repo_analysis import REPO_ANALYSIS_PROMPT
from app.agents.prompts.tasks import TASKS_GENERATION_PROMPT

# Re-export all prompts for backward compatibility
__all__ = [
    "REPO_ANALYSIS_PROMPT",
    "CURRICULUM_PLANNING_PROMPT",
    "CONCEPTS_GENERATION_PROMPT",
    "CONTENT_GENERATION_PROMPT",
    "TASKS_GENERATION_PROMPT",
]
