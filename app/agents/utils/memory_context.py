"""
Structured memory context utilities.

Returns structured data (dict) instead of prose to avoid hallucination drift.
The prompt template decides how to verbalize the structured data.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.state import RoadmapAgentState

# Configuration
MAX_COMPLETED_CONCEPTS_IN_CONTEXT = 5  # Last N concepts to include in context
MAX_SKILLS_IN_CONTEXT = 15  # Last N unique skills
MAX_FILES_IN_CONTEXT = 10  # Last N unique files


def build_structured_memory_context(
    state: "RoadmapAgentState",
    target_concept_id: str,
) -> dict:
    """
    Build structured memory context for a specific concept.

    Returns structured data (dict) instead of prose to avoid hallucination drift.
    The prompt template will decide how to verbalize this data.

    Args:
        state: Current agent state
        target_concept_id: The concept being generated

    Returns:
        Dict with structured memory context:
        {
            "previous_concepts": [{"id": "...", "title": "..."}, ...],
            "dependencies": [{"id": "...", "title": "..."}, ...],
            "files_touched": ["file1.py", ...],
            "skills_unlocked": ["skill1", ...],
            "progress": {"concepts_completed": 5, "skills_acquired": 10, ...}
        }
    """
    memory_ledger = state.get("memory_ledger", {})
    curriculum = state.get("curriculum", {})

    concepts_dict = curriculum.get("concepts", {}) if isinstance(curriculum, dict) else {}

    # Get target concept metadata
    target_concept = concepts_dict.get(target_concept_id, {})
    dependencies = target_concept.get("depends_on", [])

    # Get structured data from memory ledger
    completed_concepts = memory_ledger.get("completed_concepts", [])
    files_touched = memory_ledger.get("files_touched", [])
    skills_unlocked = memory_ledger.get("skills_unlocked", [])

    # Build structured context
    context = {
        "previous_concepts": [],
        "dependencies": [],
        "files_touched": [],
        "skills_unlocked": [],
        "progress": {
            "concepts_completed": len(completed_concepts),
            "skills_acquired": len(set(skills_unlocked)),
            "files_explored": len(set(files_touched)),
        },
    }

    # 1. Dependencies (prerequisites) - most important for coherent generation
    for dep_id in dependencies:
        if dep_id in completed_concepts:  # Only include if already completed
            dep_meta = concepts_dict.get(dep_id, {})
            context["dependencies"].append(
                {
                    "id": dep_id,
                    "title": dep_meta.get("title", dep_id),
                }
            )

    # 2. Recent completed concepts (excluding dependencies and target)
    recent_concepts = [
        c
        for c in completed_concepts[-MAX_COMPLETED_CONCEPTS_IN_CONTEXT:]
        if c not in dependencies and c != target_concept_id
    ]

    for concept_id in recent_concepts:
        concept_meta = concepts_dict.get(concept_id, {})
        context["previous_concepts"].append(
            {
                "id": concept_id,
                "title": concept_meta.get("title", concept_id),
            }
        )

    # 3. Files touched (deduplicated, limited)
    unique_files = list(dict.fromkeys(files_touched))[-MAX_FILES_IN_CONTEXT:]
    context["files_touched"] = unique_files

    # 4. Skills unlocked (deduplicated, limited)
    unique_skills = list(dict.fromkeys(skills_unlocked))[-MAX_SKILLS_IN_CONTEXT:]
    context["skills_unlocked"] = unique_skills

    return context


def format_memory_context_for_prompt(structured_context: dict) -> str:
    """
    Format structured memory context into prompt-friendly text.

    This is called by the prompt template to convert structured data
    into narrative form. The prompt decides the format.

    Args:
        structured_context: Structured memory context dict

    Returns:
        Formatted string for prompt (or default message if empty)
    """
    if not structured_context:
        return "This is the first concept - no previous learning context."

    parts = []

    # Dependencies
    if structured_context.get("dependencies"):
        parts.append("**Prerequisite Concepts (Already Learned):**")
        for dep in structured_context["dependencies"]:
            parts.append(f"- {dep['title']} ({dep['id']})")
        parts.append("")

    # Previous concepts
    if structured_context.get("previous_concepts"):
        parts.append("**Recently Completed Concepts:**")
        for prev in structured_context["previous_concepts"]:
            parts.append(f"- {prev['title']} ({prev['id']})")
        parts.append("")

    # Skills
    if structured_context.get("skills_unlocked"):
        parts.append("**Skills Acquired:**")
        parts.append(", ".join(structured_context["skills_unlocked"]))
        parts.append("")

    # Files
    if structured_context.get("files_touched"):
        parts.append("**Files Explored:**")
        for file_path in structured_context["files_touched"]:
            parts.append(f"- {file_path}")
        parts.append("")

    # Progress
    progress = structured_context.get("progress", {})
    if progress and progress.get("concepts_completed", 0) > 0:
        parts.append("**Learning Progress:**")
        parts.append(f"Concepts completed: {progress.get('concepts_completed', 0)}")
        parts.append(f"Skills acquired: {progress.get('skills_acquired', 0)}")
        parts.append(f"Files explored: {progress.get('files_explored', 0)}")

    formatted = "\n".join(parts).strip()
    return formatted if formatted else "This is the first concept - no previous learning context."
