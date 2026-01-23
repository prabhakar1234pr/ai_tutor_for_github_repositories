"""
Application startup initialization.
Call this on app startup to initialize services.
"""

import asyncio
import logging

from app.core.supabase_client import get_supabase_client
from app.services.embedding_pipeline import run_embedding_pipeline
from app.services.rate_limiter import initialize_rate_limiter

logger = logging.getLogger(__name__)


async def resume_stuck_projects():
    """
    Find and resume processing for projects stuck in 'created' status.
    This handles recovery after deployments or service restarts.
    """
    try:
        logger.info("🔍 Checking for stuck projects (status='created')...")
        supabase = get_supabase_client()

        # Find all projects with status 'created'
        projects_response = (
            supabase.table("projects")
            .select("project_id, github_url, project_name, created_at")
            .eq("status", "created")
            .execute()
        )

        if not projects_response.data:
            logger.info("✅ No stuck projects found")
            return

        stuck_projects = projects_response.data
        logger.info(f"📋 Found {len(stuck_projects)} stuck project(s) to resume")

        # Resume each stuck project
        for project in stuck_projects:
            project_id = project["project_id"]
            github_url = project["github_url"]
            project_name = project.get("project_name", "Unknown")
            created_at = project.get("created_at", "")

            try:
                logger.info(
                    f"🔄 Resuming project: {project_name} (project_id={project_id}, created_at={created_at})"
                )
                # Run pipeline in background (non-blocking)
                asyncio.create_task(
                    run_embedding_pipeline(
                        str(project_id),
                        github_url,
                        api_start_time=None,  # No API start time for recovery
                    )
                )
                logger.info(f"✅ Scheduled pipeline resume for project: {project_name}")
            except Exception as e:
                logger.error(
                    f"❌ Failed to resume project {project_name} (project_id={project_id}): {e}",
                    exc_info=True,
                )
                # Continue with other projects even if one fails

        logger.info(
            f"✅ Completed recovery check: {len(stuck_projects)} project(s) scheduled for resume"
        )

    except Exception as e:
        logger.error(f"❌ Error during stuck project recovery: {e}", exc_info=True)
        # Don't fail startup if recovery fails
        logger.warning("   Application will continue, but some projects may need manual recovery")


async def startup_services():
    """
    Initialize all services on application startup.
    Call this from FastAPI startup event.
    """
    logger.info("🚀 Initializing application services...")

    # Initialize rate limiter (will use Redis if available, fallback otherwise)
    try:
        await initialize_rate_limiter()
        logger.info("✅ Rate limiter initialized")
    except Exception as e:
        logger.warning(f"⚠️  Rate limiter initialization failed: {e}")
        logger.info("   Application will continue with reduced functionality")

    # Resume stuck projects (non-blocking, runs in background)
    try:
        await resume_stuck_projects()
    except Exception as e:
        logger.warning(f"⚠️  Stuck project recovery failed: {e}")
        # Don't block startup if recovery fails

    logger.info("✅ Startup services initialized")


async def shutdown_services():
    """
    Cleanup services on application shutdown.
    Call this from FastAPI shutdown event.
    """
    try:
        logger.info("🛑 Shutting down application services...")
        # Add any cleanup logic here
        logger.info("✅ Services shut down")
    except Exception as e:
        # Ignore cancellation errors during shutdown (normal when stopping with Ctrl+C)
        if "CancelledError" not in str(type(e).__name__):
            logger.warning(f"⚠️  Error during shutdown: {e}")
