"""
Workspace Manager Service
High-level workspace lifecycle management.
Handles creating, retrieving, and destroying Docker workspaces.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

from app.core.supabase_client import get_supabase_client
from app.services.docker_client import get_docker_client, DockerClient

logger = logging.getLogger(__name__)


@dataclass
class Workspace:
    """Workspace data model."""
    workspace_id: str
    user_id: str
    project_id: str
    container_id: Optional[str]
    container_status: str
    created_at: datetime
    last_active_at: datetime


class WorkspaceManager:
    """Manages workspace lifecycle - creation, retrieval, destruction."""

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

    def create_workspace(self, user_id: str, project_id: str) -> Workspace:
        """
        Create a new workspace with a Docker container.

        Args:
            user_id: User's UUID
            project_id: Project's UUID

        Returns:
            Created Workspace object
        """
        workspace_id = str(uuid.uuid4())
        container_name = f"gitguide-ws-{workspace_id[:8]}"

        # Create container
        container_id, status = self.docker.create_container(name=container_name)

        # Start container immediately
        self.docker.start_container(container_id)
        status = self.docker.get_container_status(container_id)

        # Save to database
        now = datetime.now(timezone.utc).isoformat()
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

        logger.info(f"Workspace created: {workspace_id} with container {container_id[:12]}")
        return self._row_to_workspace(result.data[0])

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """
        Get a workspace by its ID.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Workspace object or None if not found
        """
        result = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )

        if not result.data:
            return None

        return self._row_to_workspace(result.data[0])

    def get_workspace_by_user_project(
        self, user_id: str, project_id: str
    ) -> Optional[Workspace]:
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

        Args:
            user_id: User's UUID
            project_id: Project's UUID

        Returns:
            Workspace object (existing or newly created)
        """
        existing = self.get_workspace_by_user_project(user_id, project_id)
        if existing:
            # Update last_active_at
            self._update_last_active(existing.workspace_id)
            return existing

        return self.create_workspace(user_id, project_id)

    def destroy_workspace(self, workspace_id: str) -> bool:
        """
        Stop and remove container, delete from database.

        Args:
            workspace_id: Workspace UUID

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

        # Delete from database
        self.supabase.table(self.table_name).delete().eq(
            "workspace_id", workspace_id
        ).execute()

        logger.info(f"Workspace destroyed: {workspace_id}")
        return True

    def get_workspace_status(self, workspace_id: str) -> Optional[str]:
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

        Args:
            workspace_id: Workspace UUID

        Returns:
            True if started successfully
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace or not workspace.container_id:
            return False

        success = self.docker.start_container(workspace.container_id)
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
        workspace = self.get_workspace(workspace_id)
        if not workspace or not workspace.container_id:
            return False

        success = self.docker.stop_container(workspace.container_id)
        if success:
            self._update_status(workspace_id, "exited")

        return success

    def _update_status(self, workspace_id: str, status: str) -> None:
        """Update container status in database."""
        self.supabase.table(self.table_name).update(
            {"container_status": status}
        ).eq("workspace_id", workspace_id).execute()

    def _update_last_active(self, workspace_id: str) -> None:
        """Update last_active_at timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        self.supabase.table(self.table_name).update(
            {"last_active_at": now}
        ).eq("workspace_id", workspace_id).execute()


# Singleton instance
_workspace_manager: Optional[WorkspaceManager] = None


def get_workspace_manager() -> WorkspaceManager:
    """Get or create the WorkspaceManager singleton."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager

