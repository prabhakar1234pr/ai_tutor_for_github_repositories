"""
LangGraph agent for generating project roadmaps.
This agent creates a structured learning curriculum based on a GitHub repository.
"""

import logging
import time
from typing import Literal

from langgraph.graph import END, StateGraph

from app.agents.nodes.analyze_repo import analyze_repository
from app.agents.nodes.fetch_context import fetch_project_context
from app.agents.nodes.generate_content import (
    generate_concepts_for_day,
    generate_subconcepts_and_tasks,
    select_next_incomplete_day,
)
from app.agents.nodes.plan_curriculum import plan_and_save_curriculum
from app.agents.nodes.recovery import recover_failed_concepts
from app.agents.nodes.save_to_db import (
    insert_all_days_to_db,
    mark_day_generated,
    save_concept_content,
    save_concepts_to_db,
)
from app.agents.state import RoadmapAgentState
from app.agents.utils import calculate_recursion_limit, validate_inputs
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def should_continue_generation(state: RoadmapAgentState) -> Literal["generate_content", "end"]:
    """
    Conditional edge function: Check if we should continue generating days.

    Returns:
        "generate_content" if there are more days to generate
        "end" if all days are complete
    """
    if state.get("is_complete", False):
        logger.info("✅ All days generated. Roadmap complete!")
        return "end"

    if state.get("error"):
        logger.error(f"❌ Agent error: {state['error']}")
        return "end"

    # Check if current_day_number is within target_days
    current_day = state.get("current_day_number", 0)
    target_days = state.get("target_days", 0)

    if current_day >= target_days:
        logger.info(f"✅ Reached target days ({target_days}). Roadmap complete!")
        return "end"

    return "generate_content"


def should_generate_more_concepts(
    state: RoadmapAgentState,
) -> Literal["generate_concept_content", "mark_day_complete"]:
    """
    Conditional edge function: Check if we need to generate more concepts for current day.

    Returns:
        "generate_concept_content" if there are more concepts to fill
        "mark_day_complete" if all concepts are generated
    """
    current_concepts = state.get("current_concepts", [])
    current_concept_index = state.get("current_concept_index", 0)

    if current_concept_index >= len(current_concepts):
        logger.info(f"✅ All concepts generated for day {state.get('current_day_number', 0)}")
        return "mark_day_complete"

    return "generate_concept_content"


def build_roadmap_graph() -> StateGraph:
    """
    Build the LangGraph DAG for roadmap generation.

    Flow:
    1. Fetch project context from database
    2. Analyze repository using RAG
    3. Plan curriculum (generate all day themes upfront)
    4. Insert all days to database (Days 1-N, Day 0 is handled separately via API)
    5. Loop: Generate Days 1-N
       a. Select next incomplete day
       b. Generate concepts for day
       c. Save concepts to database
       d. Loop: Generate subconcepts + tasks for each concept
       e. Save concept content
       f. Mark day as generated
    6. End when all days complete

    Returns:
        Compiled StateGraph ready to run
    """
    logger.info("🔨 Building roadmap generation graph...")

    # Create the graph
    workflow = StateGraph(RoadmapAgentState)

    # ===== INITIALIZATION PHASE =====
    workflow.add_node("fetch_context", fetch_project_context)
    workflow.add_node("analyze_repo", analyze_repository)

    # ===== PLANNING PHASE =====
    workflow.add_node("plan_curriculum", plan_and_save_curriculum)
    workflow.add_node("insert_all_days", insert_all_days_to_db)

    # ===== CONTENT GENERATION LOOP =====
    # Note: Day 0 is handled separately via API endpoint (initialize-day0)
    workflow.add_node("select_next_day", select_next_incomplete_day)
    workflow.add_node("generate_concepts", generate_concepts_for_day)
    workflow.add_node("save_concepts", save_concepts_to_db)
    workflow.add_node("generate_concept_content", generate_subconcepts_and_tasks)
    workflow.add_node("save_concept_content", save_concept_content)
    workflow.add_node("mark_day_complete", mark_day_generated)

    # ===== RECOVERY PHASE =====
    workflow.add_node("recover_failed_concepts", recover_failed_concepts)

    # ===== EDGES =====

    # Start: fetch context
    workflow.set_entry_point("fetch_context")

    # Initialization flow
    workflow.add_edge("fetch_context", "analyze_repo")
    workflow.add_edge("analyze_repo", "plan_curriculum")
    workflow.add_edge("plan_curriculum", "insert_all_days")

    # After inserting all days, check if we need to generate content
    # Note: Day 0 is handled separately via API endpoint
    workflow.add_conditional_edges(
        "insert_all_days",
        should_continue_generation,
        {
            "generate_content": "select_next_day",
            "end": END,
        },
    )

    # Content generation loop
    workflow.add_edge("select_next_day", "generate_concepts")
    workflow.add_edge("generate_concepts", "save_concepts")

    # After saving concepts, loop through each concept to generate content
    workflow.add_conditional_edges(
        "save_concepts",
        should_generate_more_concepts,
        {
            "generate_concept_content": "generate_concept_content",
            "mark_day_complete": "mark_day_complete",
        },
    )

    # After generating content for a concept, save it and check if more concepts needed
    workflow.add_edge("generate_concept_content", "save_concept_content")
    workflow.add_conditional_edges(
        "save_concept_content",
        should_generate_more_concepts,
        {
            "generate_concept_content": "generate_concept_content",
            "mark_day_complete": "mark_day_complete",
        },
    )

    # After marking day complete, check if more days needed
    workflow.add_conditional_edges(
        "mark_day_complete",
        should_continue_generation,
        {
            "generate_content": "select_next_day",
            "end": "recover_failed_concepts",  # Go to recovery before ending
        },
    )

    # After recovery, end the workflow
    workflow.add_edge("recover_failed_concepts", END)

    # Compile the graph
    graph = workflow.compile()
    logger.info("✅ Roadmap generation graph built successfully")

    return graph


# Create singleton graph instance
_roadmap_graph = None


def get_roadmap_graph() -> StateGraph:
    """
    Get or create the roadmap generation graph (singleton).

    Returns:
        Compiled StateGraph instance
    """
    global _roadmap_graph

    if _roadmap_graph is None:
        logger.info("🔨 Creating roadmap generation graph (first use)...")
        _roadmap_graph = build_roadmap_graph()
        logger.info("✅ Roadmap graph ready")

    return _roadmap_graph


async def run_roadmap_agent(
    project_id: str,
    github_url: str,
    skill_level: str,
    target_days: int,
) -> dict:
    """
    Run the roadmap generation agent for a project.

    Args:
        project_id: UUID of the project
        github_url: GitHub repository URL
        skill_level: beginner/intermediate/advanced
        target_days: Number of days for the roadmap

    Returns:
        dict with keys:
            - success: bool
            - project_id: str
            - error: Optional[str]
    """
    logger.info(f"🚀 Starting roadmap generation agent for project_id={project_id}")
    logger.info(f"   GitHub URL: {github_url}")
    logger.info(f"   Skill Level: {skill_level}")
    logger.info(f"   Target Days: {target_days}")
    start_time = time.time()

    try:
        # Validate inputs early to avoid unnecessary work
        try:
            validate_inputs(project_id, github_url, skill_level, target_days)
        except ValueError as e:
            return {
                "success": False,
                "project_id": project_id,
                "error": f"Invalid input: {str(e)}",
                "duration_seconds": max(0.0, time.time() - start_time),
            }

        # Ensure project exists before running workflow
        try:
            supabase = get_supabase_client()
            project_response = (
                supabase.table("Projects")
                .select("project_id")
                .eq("project_id", project_id)
                .execute()
            )
            if not project_response.data:
                return {
                    "success": False,
                    "project_id": project_id,
                    "error": "Project not found",
                    "duration_seconds": max(0.0, time.time() - start_time),
                }
        except Exception as e:
            logger.error(f"Project check failed: {e}")
            return {
                "success": False,
                "project_id": project_id,
                "error": f"Project check failed: {str(e)}",
                "duration_seconds": max(0.0, time.time() - start_time),
            }

        # Initialize state
        initial_state: RoadmapAgentState = {
            "project_id": project_id,
            "github_url": github_url,
            "skill_level": skill_level,
            "target_days": target_days,
            "repo_analysis": None,
            "curriculum": [],
            "current_day_number": 0,
            "current_day_id": None,
            "current_concepts": [],
            "current_concept_index": 0,
            "day_ids_map": None,
            "concept_ids_map": None,
            "is_complete": False,
            "error": None,
        }

        # Get graph and run
        graph = get_roadmap_graph()

        # Calculate recursion limit:
        # - Each day (Days 1-N): 1 (select) + 1 (concepts) + N concepts (subconcepts/tasks) + 1 (mark complete)
        # - Day 0 is handled separately via API endpoint, not included here
        # - For 14 days with ~4 concepts each: ~14 * (1 + 1 + 4 + 1) = ~98 iterations
        config = {"recursion_limit": calculate_recursion_limit(target_days)}

        # Run the graph (LangGraph handles async execution)
        final_state = await graph.ainvoke(initial_state, config=config)

        if final_state.get("error"):
            logger.error(f"❌ Roadmap generation failed: {final_state['error']}")
            return {
                "success": False,
                "project_id": project_id,
                "error": final_state["error"],
                "duration_seconds": max(0.0, time.time() - start_time),
            }

        logger.info(f"✅ Roadmap generation completed successfully for project_id={project_id}")
        return {
            "success": True,
            "project_id": project_id,
            "error": None,
            "duration_seconds": max(0.0, time.time() - start_time),
        }

    except Exception as e:
        logger.error(f"❌ Error running roadmap agent: {e}", exc_info=True)
        return {
            "success": False,
            "project_id": project_id,
            "error": str(e),
            "duration_seconds": max(0.0, time.time() - start_time),
        }
