"""
Service to trigger roadmap generation agent as a background task.
This runs after embeddings are complete.
"""

import logging
import asyncio
from app.agents.roadmap_agent import run_roadmap_agent
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


async def run_roadmap_generation(
    project_id: str,
    github_url: str,
    skill_level: str,
    target_days: int,
):
    """
    Run the roadmap generation agent for a project.
    
    This function is designed to be called as a background task after
    embeddings are complete.
    
    Args:
        project_id: UUID of the project
        github_url: GitHub repository URL
        skill_level: beginner/intermediate/advanced
        target_days: Number of days for the roadmap
    """
    logger.info(f"🚀 Starting roadmap generation for project_id={project_id}")
    logger.info(f"   GitHub URL: {github_url}")
    logger.info(f"   Skill Level: {skill_level}")
    logger.info(f"   Target Days: {target_days}")
    
    try:
        # Run the roadmap agent
        result = await run_roadmap_agent(
            project_id=project_id,
            github_url=github_url,
            skill_level=skill_level,
            target_days=target_days,
        )
        
        if result["success"]:
            logger.info(f"✅ Roadmap generation completed successfully for project_id={project_id}")
        else:
            logger.error(f"❌ Roadmap generation failed for project_id={project_id}: {result.get('error')}")
            # Optionally update project status to indicate roadmap generation failed
            # But we don't want to mark the whole project as failed since embeddings succeeded
            
    except Exception as e:
        logger.error(f"❌ Error in roadmap generation: {e}", exc_info=True)
        # Don't raise - this is a background task, we don't want to crash the main process


def trigger_roadmap_generation_sync(
    project_id: str,
    github_url: str,
    skill_level: str,
    target_days: int,
):
    """
    Synchronous wrapper to trigger roadmap generation.
    
    This is used by FastAPI BackgroundTasks which doesn't support async directly.
    We create a new event loop here.
    
    Args:
        project_id: UUID of the project
        github_url: GitHub repository URL
        skill_level: beginner/intermediate/advanced
        target_days: Number of days for the roadmap
    """
    # Create new event loop for this background task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(
            run_roadmap_generation(
                project_id=project_id,
                github_url=github_url,
                skill_level=skill_level,
                target_days=target_days,
            )
        )
    finally:
        loop.close()

