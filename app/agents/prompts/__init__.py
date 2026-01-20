"""
Prompt templates for roadmap generation agent.
All prompts are designed to return structured JSON for parsing.

This module provides centralized access to all prompt templates.
Individual prompts are organized in separate files for better maintainability.

LLM Call Optimization (v2):
- REPO_ANALYSIS_PROMPT: 1 call (analyze repository)
- CURRICULUM_PLANNING_PROMPT: 1 call (plan all days + concepts)
- CONCEPT_GENERATION_PROMPT: 1 call per concept (content + tasks + summary combined)

Total for 56 concepts: 2 + 56 = 58 LLM calls (down from 170)
"""

# Import all prompts from individual modules
from app.agents.prompts.concept_generation import CONCEPT_GENERATION_PROMPT

# DEPRECATED: These are kept for backward compatibility but should not be used
# The combined CONCEPT_GENERATION_PROMPT replaces all three
from app.agents.prompts.concepts import CONCEPTS_GENERATION_PROMPT  # DEPRECATED
from app.agents.prompts.content import CONTENT_GENERATION_PROMPT  # DEPRECATED
from app.agents.prompts.curriculum import CURRICULUM_PLANNING_PROMPT
from app.agents.prompts.pattern_extraction import PATTERN_EXTRACTION_PROMPT
from app.agents.prompts.repo_analysis import (
    REPO_ANALYSIS_PROMPT,  # DEPRECATED: Use two-stage prompts instead
    REPO_ANALYSIS_STAGE1_PROMPT,
    REPO_ANALYSIS_STAGE2_PROMPT,
)
from app.agents.prompts.task_generation import TASK_GENERATION_PROMPT
from app.agents.prompts.tasks import TASKS_GENERATION_PROMPT  # DEPRECATED

# Re-export all prompts
__all__ = [
    # Active prompts (v2 optimized)
    "REPO_ANALYSIS_STAGE1_PROMPT",
    "REPO_ANALYSIS_STAGE2_PROMPT",
    "CURRICULUM_PLANNING_PROMPT",
    "CONCEPT_GENERATION_PROMPT",
    "TASK_GENERATION_PROMPT",
    "PATTERN_EXTRACTION_PROMPT",
    # Deprecated prompts (kept for backward compatibility)
    "REPO_ANALYSIS_PROMPT",
    "CONCEPTS_GENERATION_PROMPT",
    "CONTENT_GENERATION_PROMPT",
    "TASKS_GENERATION_PROMPT",
]
