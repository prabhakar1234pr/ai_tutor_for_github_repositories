"""
Fetch project context from Supabase.
This node retrieves project information needed for roadmap generation.
"""

import logging
from app.agents.state import RoadmapAgentState
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def fetch_project_context(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Fetch project context from Supabase database.
    
    This node retrieves the project information from the Projects table.
    The project_id, github_url, skill_level, and target_days should already
    be in the state (passed from the caller), but we verify they exist.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state (no changes, just validation)
    """
    project_id = state.get("project_id")
    github_url = state.get("github_url")
    skill_level = state.get("skill_level")
    target_days = state.get("target_days")
    
    logger.info(f"📋 Fetching project context for project_id={project_id}")
    
    # Validate required fields
    if not project_id:
        raise ValueError("project_id is required in state")
    if not github_url:
        raise ValueError("github_url is required in state")
    if not skill_level:
        raise ValueError("skill_level is required in state")
    if not target_days:
        raise ValueError("target_days is required in state")
    
    # Verify project exists in database
    supabase = get_supabase_client()
    project_response = (
        supabase.table("Projects")
        .select("project_id, project_name, github_url, skill_level, target_days, status")
        .eq("project_id", project_id)
        .execute()
    )
    
    if not project_response.data or len(project_response.data) == 0:
        raise ValueError(f"Project {project_id} not found in database")
    
    project = project_response.data[0]
    
    # Verify project status is ready (embeddings should be complete)
    if project["status"] != "ready":
        logger.warning(
            f"⚠️  Project status is '{project['status']}', expected 'ready'. "
            f"Roadmap generation may fail if embeddings are not complete."
        )
    
    logger.info(f"✅ Project context fetched:")
    logger.info(f"   Project Name: {project['project_name']}")
    logger.info(f"   GitHub URL: {github_url}")
    logger.info(f"   Skill Level: {skill_level}")
    logger.info(f"   Target Days: {target_days}")
    
    # State already has the required fields, no update needed
    return state

