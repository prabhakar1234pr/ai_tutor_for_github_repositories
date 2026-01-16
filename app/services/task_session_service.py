"""
Task Session Service
Tracks base commit per task session for accurate verification.
"""

import logging
from datetime import UTC, datetime

from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.git_service import GitService

logger = logging.getLogger(__name__)


class TaskSessionService:
    """Service for managing task sessions."""

    def __init__(self, supabase: Client | None = None, git_service: GitService | None = None):
        self.supabase = supabase or get_supabase_client()
        self.git_service = git_service or GitService()

    def start_task_session(
        self, task_id: str, user_id: str, workspace_id: str
    ) -> dict[str, object]:
        """
        Create or get an existing task session and capture base commit.
        """
        existing = (
            self.supabase.table("task_sessions")
            .select(
                "session_id, task_id, user_id, workspace_id, base_commit, current_commit, started_at, completed_at"
            )
            .eq("task_id", task_id)
            .eq("user_id", user_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )
        if existing.data:
            return {"success": True, "session": existing.data[0], "created": False}

        workspace = self._get_workspace_row(workspace_id, user_id)
        if not workspace:
            return {"success": False, "error": "Workspace not found"}

        container_id = workspace.get("container_id")
        if not container_id:
            return {"success": False, "error": "Workspace has no container"}

        rev = self.git_service.git_rev_parse(container_id, "HEAD")
        if not rev.get("success"):
            return {"success": False, "error": rev.get("error")}

        base_commit = rev.get("sha")
        now = datetime.now(UTC).isoformat()

        row = {
            "task_id": task_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "base_commit": base_commit,
            "started_at": now,
        }

        result = self.supabase.table("task_sessions").insert(row).execute()
        if not result.data:
            return {"success": False, "error": "Failed to create task session"}

        return {"success": True, "session": result.data[0], "created": True}

    def get_task_session(self, task_id: str, user_id: str, workspace_id: str) -> dict[str, object]:
        """
        Get a task session for the given task/user/workspace.
        """
        response = (
            self.supabase.table("task_sessions")
            .select(
                "session_id, task_id, user_id, workspace_id, base_commit, current_commit, started_at, completed_at"
            )
            .eq("task_id", task_id)
            .eq("user_id", user_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )
        if not response.data:
            return {"success": False, "error": "Task session not found"}
        return {"success": True, "session": response.data[0]}

    def get_session_by_id(self, session_id: str) -> dict[str, object]:
        """
        Get a task session by session_id.
        """
        session = self._get_session_by_id(session_id)
        if not session:
            return {"success": False, "error": "Task session not found"}
        return {"success": True, "session": session}

    def complete_task_session(
        self, session_id: str, current_commit: str | None = None
    ) -> dict[str, object]:
        """
        Mark a session complete and store the current commit SHA.
        """
        now = datetime.now(UTC).isoformat()
        updates: dict[str, object] = {"completed_at": now}
        if current_commit:
            updates["current_commit"] = current_commit

        result = (
            self.supabase.table("task_sessions")
            .update(updates)
            .eq("session_id", session_id)
            .execute()
        )
        if not result.data:
            return {"success": False, "error": "Failed to update task session"}
        return {"success": True, "session": result.data[0]}

    def get_diff_for_verification(self, session_id: str) -> dict[str, object]:
        """
        Compute diff from base_commit to HEAD for a session.
        """
        session = self._get_session_by_id(session_id)
        if not session:
            return {"success": False, "error": "Task session not found"}

        workspace = self._get_workspace_row(session["workspace_id"], session["user_id"])
        if not workspace:
            return {"success": False, "error": "Workspace not found"}

        container_id = workspace.get("container_id")
        if not container_id:
            return {"success": False, "error": "Workspace has no container"}

        diff = self.git_service.git_diff(
            container_id, base_commit=session["base_commit"], head_commit="HEAD"
        )
        if not diff.get("success"):
            return {"success": False, "error": diff.get("error")}

        return {
            "success": True,
            "diff": diff.get("diff", ""),
            "base_commit": session["base_commit"],
        }

    def _get_session_by_id(self, session_id: str) -> dict[str, object] | None:
        response = (
            self.supabase.table("task_sessions")
            .select(
                "session_id, task_id, user_id, workspace_id, base_commit, current_commit, started_at, completed_at"
            )
            .eq("session_id", session_id)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    def _get_workspace_row(self, workspace_id: str, user_id: str) -> dict[str, object] | None:
        response = (
            self.supabase.table("workspaces")
            .select("workspace_id, user_id, container_id")
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]
