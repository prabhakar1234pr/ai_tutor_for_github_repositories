"""
Day summary generation node.
Creates a condensed summary of a completed day for memory context.
"""

import logging

from app.agents.state import RoadmapAgentState
from app.core.supabase_client import get_supabase_client
from app.services.groq_service import get_groq_service
from app.utils.json_parser import parse_llm_json_response_async

logger = logging.getLogger(__name__)

DAY_SUMMARY_PROMPT = """You are creating a learning summary for a completed day in a coding curriculum.

**Day Information:**
- Day Number: {day_number}
- Theme: {day_theme}
- Description: {day_description}

**Concepts Covered:**
{concepts_list}

**Tasks Completed:**
{tasks_list}

**Your Task:**
Create a concise summary of what was learned in this day. Extract:
1. A brief summary text (2-3 sentences)
2. List of concept titles covered
3. Skills acquired (what the learner can now do)
4. Key code patterns/examples (brief reference to important code concepts)

**Return ONLY valid JSON object:**
{{
  "summary_text": "Brief 2-3 sentence summary of the day's learning",
  "concepts_list": ["Concept 1", "Concept 2", ...],
  "skills_acquired": ["Skill 1", "Skill 2", ...],
  "code_examples_reference": "Brief reference to key code patterns or examples"
}}

**CRITICAL:**
- Return ONLY the JSON object, no markdown formatting
- Keep summary_text concise (2-3 sentences max)
- List all concept titles exactly as they appear
- Extract practical skills (what can be done now)
- Reference key code patterns briefly
"""


async def create_day_summary(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Create a summary for the completed day and save it to day_memory_summaries.

    This node runs after a day is marked as complete. It generates a condensed
    summary that will be used as memory context for generating future days.

    Args:
        state: Current agent state with current_day_id and current_day_number

    Returns:
        Updated state (no changes, just creates summary in DB)
    """
    project_id = state.get("project_id")
    current_day_id = state.get("current_day_id")
    current_day_number = state.get("current_day_number", 0)

    if not current_day_id:
        logger.warning("   current_day_id not found, skipping day summary")
        return state

    logger.info(f"📝 Creating summary for Day {current_day_number}")

    try:
        supabase = get_supabase_client()

        # Check if summary already exists
        existing_summary = (
            supabase.table("day_memory_summaries")
            .select("day_id")
            .eq("day_id", current_day_id)
            .eq("project_id", project_id)
            .execute()
        )

        if existing_summary.data:
            logger.info(f"   Summary already exists for Day {current_day_number}, skipping")
            return state

        # Get day information
        day_response = (
            supabase.table("roadmap_days")
            .select("day_number, theme, description")
            .eq("day_id", current_day_id)
            .execute()
        )

        if not day_response.data:
            logger.warning(f"   Day {current_day_id} not found, skipping summary")
            return state

        day_data = day_response.data[0]
        day_theme = day_data["theme"]
        day_description = day_data.get("description", "")

        # Get all concepts for this day
        concepts_response = (
            supabase.table("concepts")
            .select("concept_id, title, description, content")
            .eq("day_id", current_day_id)
            .order("order_index", desc=False)
            .execute()
        )

        concepts = concepts_response.data if concepts_response.data else []

        if not concepts:
            logger.warning(f"   No concepts found for Day {current_day_number}, skipping summary")
            return state

        # Build concepts list string
        concepts_list_parts = []
        for concept in concepts:
            concepts_list_parts.append(f"- {concept['title']}: {concept.get('description', '')}")
        concepts_list_str = "\n".join(concepts_list_parts)

        # Get all tasks for this day (through concepts)
        concept_ids = [c["concept_id"] for c in concepts]
        tasks_response = (
            supabase.table("tasks")
            .select("title, description, task_type")
            .in_("concept_id", concept_ids)
            .order("order_index", desc=False)
            .execute()
        )

        tasks = tasks_response.data if tasks_response.data else []

        # Build tasks list string
        tasks_list_parts = []
        for task in tasks:
            tasks_list_parts.append(f"- {task['title']} ({task.get('task_type', 'coding')})")
        tasks_list_str = "\n".join(tasks_list_parts) if tasks_list_parts else "No tasks"

        # Generate summary using LLM
        prompt = DAY_SUMMARY_PROMPT.format(
            day_number=current_day_number,
            day_theme=day_theme,
            day_description=day_description,
            concepts_list=concepts_list_str,
            tasks_list=tasks_list_str,
        )

        groq_service = get_groq_service()
        system_prompt = (
            "You are an expert educator creating learning summaries. "
            "Return ONLY valid JSON object, no markdown, no extra text."
        )

        logger.debug("   Calling LLM to generate day summary...")
        llm_response = await groq_service.generate_response_async(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",
        )

        # Parse JSON response
        summary_data = await parse_llm_json_response_async(llm_response, expected_type="object")

        # Extract summary fields
        summary_text = summary_data.get("summary_text", "")
        concepts_list = summary_data.get("concepts_list", [])
        skills_acquired = summary_data.get("skills_acquired", [])
        code_examples_reference = summary_data.get("code_examples_reference", "")

        # Ensure concepts_list matches actual concepts if LLM didn't provide it correctly
        if not concepts_list or len(concepts_list) != len(concepts):
            concepts_list = [c["title"] for c in concepts]

        # Save to database
        summary_insert = {
            "day_id": current_day_id,
            "project_id": project_id,
            "summary_text": summary_text,
            "concepts_list": concepts_list,
            "skills_acquired": skills_acquired,
            "code_examples_reference": code_examples_reference,
        }

        supabase.table("day_memory_summaries").insert(summary_insert).execute()

        logger.info(f"   ✅ Day {current_day_number} summary created successfully")
        logger.debug(f"   Summary: {summary_text[:100]}...")

        return state

    except Exception as e:
        logger.error(f"❌ Failed to create day summary: {e}", exc_info=True)
        # Don't fail the workflow - summary is helpful but not critical
        # The memory node will handle missing summaries gracefully
        return state
