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
    Find and resume processing for projects stuck in 'created' or 'processing' status.
    This handles recovery after deployments or service restarts.

    Projects in 'processing' status for >30 minutes are considered stuck and reset to 'created'.
    """
    try:
        import datetime

        logger.info("🔍 Checking for stuck projects...")
        supabase = get_supabase_client()

        # Find all projects with status 'created' (never started)
        created_projects_response = (
            supabase.table("projects")
            .select("project_id, github_url, project_name, created_at, updated_at")
            .eq("status", "created")
            .execute()
        )

        # Find projects stuck in 'processing' status (likely interrupted)
        # Reset them to 'created' if they've been processing for >30 minutes
        processing_projects_response = (
            supabase.table("projects")
            .select("project_id, github_url, project_name, created_at, updated_at")
            .eq("status", "processing")
            .execute()
        )

        stuck_projects = []

        # Add projects with 'created' status
        if created_projects_response.data:
            stuck_projects.extend(created_projects_response.data)
            logger.info(
                f"📋 Found {len(created_projects_response.data)} project(s) with status 'created'"
            )

        # Check for projects stuck in 'processing' status
        if processing_projects_response.data:
            now = datetime.datetime.now(datetime.UTC)
            reset_count = 0

            for project in processing_projects_response.data:
                updated_at_str = project.get("updated_at")
                if updated_at_str:
                    try:
                        # Parse the timestamp
                        if isinstance(updated_at_str, str):
                            updated_at = datetime.datetime.fromisoformat(
                                updated_at_str.replace("Z", "+00:00")
                            )
                        else:
                            updated_at = updated_at_str

                        # Check if stuck for >30 minutes
                        time_diff = (now - updated_at).total_seconds() / 60  # minutes

                        if time_diff > 30:
                            # Reset to 'created' so it can be retried
                            project_id = project["project_id"]
                            logger.warning(
                                f"⚠️  Project {project.get('project_name', 'Unknown')} "
                                f"(project_id={project_id}) stuck in 'processing' for {time_diff:.1f} minutes. "
                                f"Resetting to 'created' status."
                            )
                            supabase.table("projects").update({"status": "created"}).eq(
                                "project_id", project_id
                            ).execute()
                            stuck_projects.append(project)
                            reset_count += 1
                        else:
                            logger.debug(
                                f"   Project {project.get('project_name', 'Unknown')} "
                                f"in 'processing' for {time_diff:.1f} minutes (still within limit)"
                            )
                    except Exception as parse_error:
                        logger.warning(
                            f"⚠️  Could not parse timestamp for project {project.get('project_id')}: {parse_error}"
                        )
                        # If we can't parse, assume it's stuck and reset
                        project_id = project["project_id"]
                        supabase.table("projects").update({"status": "created"}).eq(
                            "project_id", project_id
                        ).execute()
                        stuck_projects.append(project)
                        reset_count += 1

            if reset_count > 0:
                logger.info(
                    f"🔄 Reset {reset_count} stuck 'processing' project(s) to 'created' status"
                )

        if not stuck_projects:
            logger.info("✅ No stuck projects found")
            return

        logger.info(f"📋 Total stuck projects to resume: {len(stuck_projects)}")

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
                # Using asyncio.create_task ensures it runs asynchronously
                # The pipeline itself handles status updates and errors
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
