"""
Cleanup script to delete all workspaces and terminal sessions.
This will:
1. Get all workspaces from the database
2. Delete all terminal sessions for each workspace
3. Destroy all workspaces (stops containers, removes containers, deletes volumes)
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.terminal_service import get_terminal_service
from app.services.workspace_manager import get_workspace_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cleanup_all_workspaces():
    """Delete all workspaces and their terminal sessions."""
    workspace_manager = get_workspace_manager()
    terminal_service = get_terminal_service()

    # Get all workspaces
    workspaces = workspace_manager.get_all_workspaces()
    logger.info(f"Found {len(workspaces)} workspace(s) to clean up")

    if not workspaces:
        logger.info("No workspaces found. Nothing to clean up.")
        return

    total_sessions_deleted = 0
    successful_deletions = 0
    failed_deletions = 0

    for workspace in workspaces:
        workspace_id = workspace.workspace_id
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Cleaning up workspace: {workspace_id[:8]}...")
        logger.info(
            f"  Container ID: {workspace.container_id[:12] if workspace.container_id else 'None'}"
        )
        logger.info(f"  Status: {workspace.container_status}")

        try:
            # Delete terminal sessions for this workspace
            sessions_deleted = terminal_service.delete_sessions_for_workspace(workspace_id)
            total_sessions_deleted += sessions_deleted
            logger.info(f"  ✅ Deleted {sessions_deleted} terminal session(s)")

            # Destroy workspace (stops container, removes container, deletes volume)
            success = workspace_manager.destroy_workspace(workspace_id, delete_volume=True)
            if success:
                successful_deletions += 1
                logger.info("  ✅ Destroyed workspace (container and volume)")
            else:
                failed_deletions += 1
                logger.warning("  ⚠️  Failed to destroy workspace")

        except Exception as e:
            failed_deletions += 1
            logger.error(f"  ❌ Error cleaning up workspace {workspace_id[:8]}: {e}", exc_info=True)

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info("CLEANUP SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Total workspaces processed: {len(workspaces)}")
    logger.info(f"Successfully deleted: {successful_deletions}")
    logger.info(f"Failed to delete: {failed_deletions}")
    logger.info(f"Total terminal sessions deleted: {total_sessions_deleted}")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        logger.info("Starting cleanup of all workspaces and terminal sessions...")
        cleanup_all_workspaces()
        logger.info("\n✅ Cleanup completed!")
    except Exception as e:
        logger.error(f"❌ Fatal error during cleanup: {e}", exc_info=True)
        sys.exit(1)
