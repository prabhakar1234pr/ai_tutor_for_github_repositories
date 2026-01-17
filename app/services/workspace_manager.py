"""
Workspace Manager Service
High-level workspace lifecycle management.
Handles creating, retrieving, and destroying Docker workspaces.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.supabase_client import get_supabase_client
from app.services.docker_client import DockerClient, get_docker_client
from app.services.git_service import GitService

logger = logging.getLogger(__name__)


@dataclass
class Workspace:
    """Workspace data model."""

    workspace_id: str
    user_id: str
    project_id: str
    container_id: str | None
    container_status: str
    created_at: datetime
    last_active_at: datetime


class WorkspaceManager:
    """
    Manages workspace lifecycle - creation, retrieval, destruction.

    # ==========================================================================
    # GCP DEPLOYMENT: Single VM with Docker (No code changes needed)
    # ==========================================================================
    # This implementation works as-is on a GCP Compute Engine VM.
    #
    # DEPLOYMENT STEPS:
    #   1. Create VM: e2-small, Ubuntu 22.04, 30GB persistent disk
    #   2. Install Docker: sudo apt install docker.io docker-compose -y
    #   3. Clone repo and run FastAPI backend
    #   4. Build workspace image: docker build -t gitguide-workspace -f docker/Dockerfile.workspace .
    #   5. Set up domain + HTTPS (Caddy or nginx + Let's Encrypt)
    #
    # HOW IT WORKS:
    #   - Docker runs directly on the VM
    #   - Docker volumes stored in /var/lib/docker/volumes/ on persistent disk
    #   - User files persist across container restarts, Docker restarts, VM reboots
    #
    # COST:
    #   - e2-small: ~$15/month
    #   - 30GB disk: ~$3/month
    #   - Total: ~$18/month → $300 credits last 16+ months
    #
    # DATA SAFETY:
    #   - Container deleted → files safe (volume persists)
    #   - Docker restarted → files safe
    #   - VM rebooted → files safe
    #   - VM deleted → files LOST (don't delete the VM)
    # ==========================================================================
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.docker: DockerClient = get_docker_client()
        self.table_name = "workspaces"

    def _row_to_workspace(self, row: dict) -> Workspace:
        """Convert database row to Workspace object."""
        return Workspace(
            workspace_id=row["workspace_id"],
            user_id=row["user_id"],
            project_id=row["project_id"],
            container_id=row.get("container_id"),
            container_status=row.get("container_status", "unknown"),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            last_active_at=datetime.fromisoformat(row["last_active_at"].replace("Z", "+00:00")),
        )

    def _get_volume_name(self, workspace_id: str) -> str:
        """Generate a consistent volume name for a workspace."""
        return f"gitguide-vol-{workspace_id[:8]}"

    def create_workspace(self, user_id: str, project_id: str) -> Workspace:
        """
        Create a new workspace with a Docker container and persistent volume.

        Args:
            user_id: User's UUID
            project_id: Project's UUID

        Returns:
            Created Workspace object
        """
        workspace_id = str(uuid.uuid4())
        container_name = f"gitguide-ws-{workspace_id[:8]}"
        volume_name = self._get_volume_name(workspace_id)

        # Create container with persistent volume
        container_id, status = self.docker.create_container(
            name=container_name, volume_name=volume_name
        )

        # Start container immediately
        self.docker.start_container(container_id)
        status = self.docker.get_container_status(container_id)

        # Save to database
        now = datetime.now(UTC).isoformat()
        row = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "project_id": project_id,
            "container_id": container_id,
            "container_status": status,
            "created_at": now,
            "last_active_at": now,
        }

        result = self.supabase.table(self.table_name).insert(row).execute()

        if not result.data:
            # Cleanup container if DB insert failed
            self.docker.remove_container(container_id)
            raise RuntimeError("Failed to save workspace to database")

        logger.info(
            f"Workspace created: {workspace_id} with container {container_id[:12]} and volume {volume_name}"
        )
        return self._row_to_workspace(result.data[0])

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        """
        Get a workspace by its ID.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Workspace object or None if not found
        """
        logger.debug(f"[GET_WORKSPACE] Looking up workspace: {workspace_id}")
        result = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )

        if not result.data:
            logger.debug(f"[GET_WORKSPACE] Workspace not found: {workspace_id}")
            return None

        workspace = self._row_to_workspace(result.data[0])
        logger.debug(
            f"[GET_WORKSPACE] Found workspace: {workspace_id}, container: {workspace.container_id[:12] if workspace.container_id else 'None'}, status: {workspace.container_status}"
        )
        return workspace

    def get_workspace_by_user_project(self, user_id: str, project_id: str) -> Workspace | None:
        """
        Get existing workspace for a user-project pair.

        Args:
            user_id: User's UUID
            project_id: Project's UUID

        Returns:
            Workspace object or None if not found
        """
        result = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("user_id", user_id)
            .eq("project_id", project_id)
            .execute()
        )

        if not result.data:
            return None

        return self._row_to_workspace(result.data[0])

    def get_or_create_workspace(self, user_id: str, project_id: str) -> Workspace:
        """
        Get existing workspace or create new one.
        Also handles orphaned workspaces where the container was deleted.

        Args:
            user_id: User's UUID
            project_id: Project's UUID

        Returns:
            Workspace object (existing or newly created)
        """
        logger.info(f"[GET_OR_CREATE] user={user_id}, project={project_id}")
        existing = self.get_workspace_by_user_project(user_id, project_id)
        if existing:
            logger.debug(f"[GET_OR_CREATE] Found existing workspace: {existing.workspace_id}")
            # Check if container actually exists in Docker
            if existing.container_id:
                container_exists = self.docker.container_exists(existing.container_id)
                logger.debug(
                    f"[GET_OR_CREATE] Container {existing.container_id[:12]} exists: {container_exists}"
                )
                if not container_exists:
                    # Container was deleted (orphaned workspace) - recreate it
                    logger.warning(
                        f"Container {existing.container_id[:12]} not found for workspace {existing.workspace_id}. "
                        "Recreating container..."
                    )
                    return self._recreate_container(existing)

            # Update last_active_at
            self._update_last_active(existing.workspace_id)
            logger.info(f"[GET_OR_CREATE] Returning existing workspace: {existing.workspace_id}")
            return existing

        logger.info("[GET_OR_CREATE] No existing workspace, creating new one")
        return self.create_workspace(user_id, project_id)

    def _recreate_container(self, workspace: Workspace) -> Workspace:
        """
        Recreate a container for an orphaned workspace.
        Reuses the existing volume so user files are preserved.

        Args:
            workspace: Existing workspace with missing container

        Returns:
            Updated Workspace object with new container
        """
        container_name = f"gitguide-ws-{workspace.workspace_id[:8]}"
        volume_name = self._get_volume_name(workspace.workspace_id)

        # Create new container with existing volume (files are preserved)
        container_id, status = self.docker.create_container(
            name=container_name, volume_name=volume_name
        )

        # Start container immediately
        self.docker.start_container(container_id)
        status = self.docker.get_container_status(container_id)

        # Update database with new container_id
        now = datetime.now(UTC).isoformat()
        self.supabase.table(self.table_name).update(
            {
                "container_id": container_id,
                "container_status": status,
                "last_active_at": now,
            }
        ).eq("workspace_id", workspace.workspace_id).execute()

        logger.info(
            f"Recreated container {container_id[:12]} for workspace {workspace.workspace_id} "
            f"with volume {volume_name} (files preserved)"
        )

        # Return updated workspace
        return Workspace(
            workspace_id=workspace.workspace_id,
            user_id=workspace.user_id,
            project_id=workspace.project_id,
            container_id=container_id,
            container_status=status,
            created_at=workspace.created_at,
            last_active_at=datetime.now(UTC),
        )

    def destroy_workspace(self, workspace_id: str, delete_volume: bool = True) -> bool:
        """
        Stop and remove container, delete from database, and optionally delete volume.

        Args:
            workspace_id: Workspace UUID
            delete_volume: If True, also delete the persistent volume (default: True)

        Returns:
            True if destroyed successfully
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            logger.warning(f"Workspace not found: {workspace_id}")
            return False

        # Stop and remove container
        if workspace.container_id:
            self.docker.stop_container(workspace.container_id)
            self.docker.remove_container(workspace.container_id)

        # Remove volume if requested
        if delete_volume:
            volume_name = self._get_volume_name(workspace_id)
            self.docker.remove_volume(volume_name)
            logger.info(f"Volume {volume_name} removed")

        # Delete from database
        self.supabase.table(self.table_name).delete().eq("workspace_id", workspace_id).execute()

        logger.info(f"Workspace destroyed: {workspace_id}")
        return True

    def initialize_git_repo(
        self, workspace_id: str, user_id: str, author_name: str, author_email: str
    ) -> dict:
        """
        Clone and configure the user's repository in the workspace.
        Returns status info for API responses.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return {"success": False, "error": "Workspace not found"}
        if workspace.user_id != user_id:
            return {"success": False, "error": "Access denied"}
        if not workspace.container_id:
            return {"success": False, "error": "Workspace has no container"}
        if workspace.container_status != "running":
            return {
                "success": False,
                "error": f"Container not running ({workspace.container_status})",
            }

        project_response = (
            self.supabase.table("projects")
            .select("project_id, user_repo_url, github_access_token")
            .eq("project_id", workspace.project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not project_response.data:
            return {"success": False, "error": "Project not found"}

        project = project_response.data[0]
        repo_url = project.get("user_repo_url")
        token = project.get("github_access_token")
        if not repo_url or not token:
            return {"success": False, "error": "Repository URL or GitHub token missing"}

        git_service = GitService()
        clone_result = git_service.clone_repository(workspace.container_id, repo_url, token=token)
        if clone_result.get("status") == "error":
            return {"success": False, "error": clone_result.get("message", "Clone failed")}

        config_result = git_service.configure_git_user(
            workspace.container_id, author_name, author_email
        )
        if not config_result.get("success"):
            return {
                "success": False,
                "error": config_result.get("error", "Failed to configure git user"),
            }

        branch_result = git_service.git_current_branch(workspace.container_id)
        branch = branch_result.get("branch") if branch_result.get("success") else "main"
        rev_result = git_service.git_rev_parse(workspace.container_id, "HEAD")
        last_commit = rev_result.get("sha") if rev_result.get("success") else None

        workspace_row = (
            self.supabase.table(self.table_name)
            .select("last_platform_commit")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        existing_last_commit = None
        if workspace_row.data:
            existing_last_commit = workspace_row.data[0].get("last_platform_commit")

        update_data = {
            "git_remote_url": repo_url,
            "current_branch": branch,
        }
        if last_commit and not existing_last_commit:
            update_data["last_platform_commit"] = last_commit

        self.supabase.table(self.table_name).update(update_data).eq(
            "workspace_id", workspace_id
        ).execute()

        return {
            "success": True,
            "status": clone_result.get("status"),
            "branch": branch,
            "last_platform_commit": last_commit,
        }

    def get_workspace_status(self, workspace_id: str) -> str | None:
        """
        Get current container status for a workspace.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Status string or None if workspace not found
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace or not workspace.container_id:
            return None

        # Get live status from Docker
        status = self.docker.get_container_status(workspace.container_id)

        # Update in database if changed
        if status != workspace.container_status:
            self._update_status(workspace_id, status)

        return status

    def start_workspace(self, workspace_id: str) -> bool:
        """
        Start a stopped workspace container.
        If container doesn't exist, recreate it.

        Args:
            workspace_id: Workspace UUID

        Returns:
            True if started successfully
        """
        logger.info(f"[START_WORKSPACE] Starting workspace: {workspace_id}")
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            logger.warning(f"[START_WORKSPACE] Workspace not found: {workspace_id}")
            return False

        # Check if container exists
        if workspace.container_id:
            container_exists = self.docker.container_exists(workspace.container_id)
            logger.debug(
                f"[START_WORKSPACE] Container {workspace.container_id[:12]} exists: {container_exists}"
            )
            if not container_exists:
                # Container was deleted - recreate it
                logger.warning(f"Container {workspace.container_id[:12]} not found. Recreating...")
                self._recreate_container(workspace)
                return True

        if not workspace.container_id:
            logger.error(f"[START_WORKSPACE] No container_id for workspace: {workspace_id}")
            return False

        success = self.docker.start_container(workspace.container_id)
        logger.info(f"[START_WORKSPACE] Container start result: {success}")
        if success:
            self._update_status(workspace_id, "running")
            self._update_last_active(workspace_id)

        return success

    def stop_workspace(self, workspace_id: str) -> bool:
        """
        Stop a running workspace container.

        Args:
            workspace_id: Workspace UUID

        Returns:
            True if stopped successfully
        """
        logger.info(f"[STOP_WORKSPACE] Stopping workspace: {workspace_id}")
        workspace = self.get_workspace(workspace_id)
        if not workspace or not workspace.container_id:
            logger.warning(f"[STOP_WORKSPACE] Workspace or container not found: {workspace_id}")
            return False

        success = self.docker.stop_container(workspace.container_id)
        logger.info(f"[STOP_WORKSPACE] Container stop result: {success}")
        if success:
            self._update_status(workspace_id, "exited")

        return success

    def _update_status(self, workspace_id: str, status: str) -> None:
        """Update container status in database."""
        self.supabase.table(self.table_name).update({"container_status": status}).eq(
            "workspace_id", workspace_id
        ).execute()

    def _update_last_active(self, workspace_id: str) -> None:
        """Update last_active_at timestamp."""
        now = datetime.now(UTC).isoformat()
        self.supabase.table(self.table_name).update({"last_active_at": now}).eq(
            "workspace_id", workspace_id
        ).execute()


# Singleton instance
_workspace_manager: WorkspaceManager | None = None


def get_workspace_manager() -> WorkspaceManager:
    """Get or create the WorkspaceManager singleton."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager
