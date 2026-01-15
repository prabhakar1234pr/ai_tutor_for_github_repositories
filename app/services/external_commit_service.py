"""
External Commit Detection Service
Detects commits made outside the platform and resets when consented.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.git_service import GitService
from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class ExternalCommitService:
    """Service for detecting and resetting external commits."""

    def __init__(
        self,
        supabase: Optional[Client] = None,
        workspace_manager: Optional[WorkspaceManager] = None,
        git_service: Optional[GitService] = None,
    ):
        self.supabase = supabase or get_supabase_client()
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.git_service = git_service or GitService()

    def check_external_commits(self, workspace_id: str, user_id: str) -> Dict[str, object]:
        """
        Detect external commits by comparing last_platform_commit with remote HEAD.
        """
        workspace = self._get_workspace_row(workspace_id, user_id)
        if not workspace:
            return {"success": False, "error": "Workspace not found"}

        last_platform_commit = workspace.get("last_platform_commit")
        if not last_platform_commit:
            return {
                "success": True,
                "has_external_commits": False,
                "reason": "no_platform_commit",
            }

        container_id = workspace.get("container_id")
        if not container_id:
            return {"success": False, "error": "Workspace has no container"}

        project = self._get_project_row(workspace.get("project_id"), user_id)
        if not project:
            return {"success": False, "error": "Project not found"}

        branch = workspace.get("current_branch") or "main"
        remote_url = workspace.get("git_remote_url") or project.get("user_repo_url")
        if not remote_url:
            return {"success": False, "error": "Remote URL not found"}

        token = project.get("github_access_token")
        remote_url = self._apply_token(remote_url, token)

        ls_remote = self.git_service.git_ls_remote(container_id, remote_url, branch)
        if not ls_remote.get("success"):
            return {"success": False, "error": ls_remote.get("error")}

        remote_sha = ls_remote.get("sha")
        if not remote_sha:
            return {"success": False, "error": "Failed to get remote SHA"}

        if remote_sha == last_platform_commit:
            return {
                "success": True,
                "has_external_commits": False,
                "last_platform_commit": last_platform_commit,
                "remote_commit": remote_sha,
            }

        log = self.git_service.git_log(
            container_id,
            range_spec=f"{last_platform_commit}..{remote_sha}",
            max_count=100,
        )
        commits = log.get("commits", []) if log.get("success") else []

        return {
            "success": True,
            "has_external_commits": True,
            "last_platform_commit": last_platform_commit,
            "remote_commit": remote_sha,
            "external_commits": commits,
        }

    def reset_to_platform_commit(self, workspace_id: str, user_id: str, confirmed: bool) -> Dict[str, object]:
        """
        Hard reset to last_platform_commit and force push (if consented).
        """
        if not confirmed:
            return {"success": False, "error": "Confirmation required"}

        workspace = self._get_workspace_row(workspace_id, user_id)
        if not workspace:
            return {"success": False, "error": "Workspace not found"}

        last_platform_commit = workspace.get("last_platform_commit")
        if not last_platform_commit:
            return {"success": False, "error": "No last_platform_commit recorded"}

        container_id = workspace.get("container_id")
        if not container_id:
            return {"success": False, "error": "Workspace has no container"}

        project = self._get_project_row(workspace.get("project_id"), user_id)
        if not project:
            return {"success": False, "error": "Project not found"}

        if not project.get("github_consent_accepted"):
            return {"success": False, "error": "Consent not accepted for this project"}

        reset_result = self.git_service.git_reset_hard(container_id, last_platform_commit)
        if not reset_result.get("success"):
            return {"success": False, "error": reset_result.get("error")}

        branch = workspace.get("current_branch") or "main"
        token = project.get("github_access_token")
        push_result = None
        if token:
            push_result = self.git_service.git_push(container_id, branch, token=token, force=True)
            if not push_result.get("success"):
                return {"success": False, "error": push_result.get("error")}

        now = datetime.now(timezone.utc).isoformat()
        self.supabase.table("workspaces").update(
            {"last_platform_commit": last_platform_commit, "updated_at": now}
        ).eq("workspace_id", workspace_id).eq("user_id", user_id).execute()

        return {
            "success": True,
            "reset_commit": last_platform_commit,
            "push_result": push_result,
        }

    def get_external_commits_list(self, workspace_id: str, user_id: str) -> Dict[str, object]:
        """
        Convenience method to return external commits list.
        """
        result = self.check_external_commits(workspace_id, user_id)
        if not result.get("success"):
            return result
        return {
            "success": True,
            "external_commits": result.get("external_commits", []),
            "has_external_commits": result.get("has_external_commits", False),
        }

    def _get_workspace_row(self, workspace_id: str, user_id: str) -> Optional[Dict[str, object]]:
        response = (
            self.supabase.table("workspaces")
            .select(
                "workspace_id, user_id, project_id, container_id, last_platform_commit, current_branch, git_remote_url"
            )
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    def _get_project_row(self, project_id: Optional[str], user_id: str) -> Optional[Dict[str, object]]:
        if not project_id:
            return None
        response = (
            self.supabase.table("Projects")
            .select("project_id, user_id, user_repo_url, github_access_token, github_consent_accepted")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    @staticmethod
    def _apply_token(repo_url: str, token: Optional[str]) -> str:
        if not token:
            return repo_url
        if repo_url.startswith("https://"):
            return repo_url.replace("https://", f"https://x-access-token:{token}@")
        if repo_url.startswith("http://"):
            return repo_url.replace("http://", f"http://x-access-token:{token}@")
        return repo_url
