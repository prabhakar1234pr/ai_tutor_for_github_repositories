"""
Git API Router
REST endpoints for git operations inside workspace containers.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client
import logging
from typing import Optional
import re

from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import get_user_id_from_clerk
from app.services.workspace_manager import get_workspace_manager, WorkspaceManager
from app.services.git_service import GitService
from app.services.external_commit_service import ExternalCommitService

router = APIRouter()
logger = logging.getLogger(__name__)


class CommitRequest(BaseModel):
    message: str = Field(..., description="Commit message")
    author_name: Optional[str] = None
    author_email: Optional[str] = None


class PushRequest(BaseModel):
    branch: str = Field(default="main", description="Branch name")
    force: bool = False


class PullRequest(BaseModel):
    branch: str = Field(default="main", description="Branch name")
    handle_uncommitted: Optional[str] = Field(
        default=None,
        description="How to handle uncommitted changes: commit|stash|discard"
    )


class ResetExternalRequest(BaseModel):
    confirmed: bool = Field(..., description="User confirmed reset")


def _get_container_id(
    workspace_id: str,
    user_id: str,
    workspace_manager: WorkspaceManager,
) -> str:
    """Get container ID for a workspace, verifying ownership and status."""
    workspace = workspace_manager.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this workspace")

    if not workspace.container_id:
        raise HTTPException(status_code=400, detail="Workspace has no container")

    if workspace.container_status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Workspace container is not running (status: {workspace.container_status})"
        )

    return workspace.container_id


def _get_project_token(supabase: Client, project_id: str, user_id: str) -> Optional[str]:
    response = (
        supabase.table("Projects")
        .select("github_access_token")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0].get("github_access_token")


def _get_project_repo_url(supabase: Client, project_id: str, user_id: str) -> Optional[str]:
    response = (
        supabase.table("Projects")
        .select("user_repo_url, github_url")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        return None
    project = response.data[0]
    return project.get("user_repo_url") or project.get("github_url")


def _normalize_repo_url(url: str) -> str:
    """
    Normalize repo URL by stripping all auth and normalizing format.
    Handles URLs with multiple @ signs.
    """
    cleaned = url.strip()
    # Strip all auth patterns (handles multiple @ signs)
    # Extract protocol and domain/path, removing everything between protocol and domain
    match = re.match(r"(https?://)(?:[^@]+@)+([^/]+(?:/.*)?)", cleaned)
    if match:
        cleaned = match.group(1) + match.group(2)
    else:
        # Fallback: simple strip of first auth pattern
        cleaned = re.sub(r"^(https?://)[^@]+@", r"\1", cleaned)
    # Remove .git suffix
    cleaned = cleaned[:-4] if cleaned.endswith(".git") else cleaned
    # Remove trailing slash
    return cleaned.rstrip("/")


@router.get("/{workspace_id}/status")
def get_status(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    container_id = _get_container_id(workspace_id, user_id, workspace_manager)
    git_service = GitService()

    result = git_service.git_status(container_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to get git status"))

    return result


@router.get("/{workspace_id}/diff")
def get_diff(
    workspace_id: str,
    base_commit: Optional[str] = Query(default=None),
    head_commit: Optional[str] = Query(default=None),
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    container_id = _get_container_id(workspace_id, user_id, workspace_manager)
    git_service = GitService()

    result = git_service.git_diff(container_id, base_commit=base_commit, head_commit=head_commit)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to get git diff"))

    return result


@router.post("/{workspace_id}/commit")
def commit_changes(
    workspace_id: str,
    request: CommitRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    container_id = _get_container_id(workspace_id, user_id, workspace_manager)
    git_service = GitService()

    author_name = request.author_name or user_info.get("name") or "GitGuide"
    author_email = request.author_email or user_info.get("email") or "noreply@gitguide.local"

    result = git_service.git_commit(container_id, request.message, author_name, author_email)
    if not result.get("success"):
        error_msg = result.get("error", "Failed to commit")
        if "nothing to commit" in error_msg.lower():
            logger.info(f"Nothing to commit for workspace {workspace_id}")
            raise HTTPException(status_code=400, detail="Nothing to commit - no changes detected")
        logger.error(f"Commit failed for workspace {workspace_id}: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

    return result


@router.post("/{workspace_id}/push")
def push_changes(
    workspace_id: str,
    request: PushRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    workspace = workspace_manager.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this workspace")

    container_id = _get_container_id(workspace_id, user_id, workspace_manager)
    token = _get_project_token(supabase, workspace.project_id, user_id)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token not configured for this project")

    git_service = GitService()
    repo_url = _get_project_repo_url(supabase, workspace.project_id, user_id)
    if repo_url:
        # Always reset to clean repo URL from database (without auth) before pushing
        # This ensures we start from a known good state
        clean_repo_url = _normalize_repo_url(repo_url)
        # Ensure it's a full URL (add https:// if missing)
        if not clean_repo_url.startswith(("http://", "https://")):
            clean_repo_url = f"https://{clean_repo_url}"
        set_result = git_service.git_set_remote_url(container_id, clean_repo_url)
        if not set_result.get("success"):
            logger.warning(f"Failed to reset remote URL: {set_result.get('error')}, continuing anyway")

    result = git_service.git_push(container_id, request.branch, token=token, force=request.force)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to push"))

    # Update last_platform_commit after successful push
    # This ensures commits made through the platform are tracked correctly
    # Wrap in try-except to ensure push success is returned even if update fails
    try:
        head_result = git_service.git_rev_parse(container_id, "HEAD")
        if head_result.get("success") and head_result.get("sha"):
            supabase.table("workspaces").update({
                "last_platform_commit": head_result.get("sha")
            }).eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
            logger.info(f"Updated last_platform_commit to {head_result.get('sha')[:7]} for workspace {workspace_id}")
    except Exception as e:
        logger.warning(f"Failed to update last_platform_commit for workspace {workspace_id}: {e}")
        # Don't fail the push if database update fails

    return result


@router.post("/{workspace_id}/pull")
def pull_changes(
    workspace_id: str,
    request: PullRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    workspace = workspace_manager.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this workspace")

    container_id = _get_container_id(workspace_id, user_id, workspace_manager)
    token = _get_project_token(supabase, workspace.project_id, user_id)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token not configured for this project")

    git_service = GitService()
    repo_url = _get_project_repo_url(supabase, workspace.project_id, user_id)
    if repo_url:
        current_remote = git_service.git_get_remote_url(container_id)
        if current_remote.get("success"):
            current = _normalize_repo_url(current_remote.get("url", ""))
            desired = _normalize_repo_url(repo_url)
            if current and desired and current != desired:
                set_result = git_service.git_set_remote_url(container_id, repo_url)
                if not set_result.get("success"):
                    raise HTTPException(status_code=500, detail=set_result.get("error", "Failed to update remote"))

    uncommitted = git_service.git_check_uncommitted(container_id)
    if not uncommitted.get("success"):
        raise HTTPException(status_code=500, detail=uncommitted.get("error", "Failed to check changes"))

    if uncommitted.get("has_changes"):
        action = (request.handle_uncommitted or "").lower()
        if action == "commit":
            author_name = user_info.get("name") or "GitGuide"
            author_email = user_info.get("email") or "noreply@gitguide.local"
            commit_message = "WIP: auto-commit before pull"
            commit_result = git_service.git_commit(
                container_id,
                commit_message,
                author_name=author_name,
                author_email=author_email,
            )
            if not commit_result.get("success"):
                raise HTTPException(status_code=500, detail=commit_result.get("error", "Failed to auto-commit"))
        elif action == "stash":
            stash_result = git_service.git_stash(container_id, "WIP: auto-stash before pull")
            if not stash_result.get("success"):
                raise HTTPException(status_code=500, detail=stash_result.get("error", "Failed to stash changes"))
        elif action == "discard":
            discard_result = git_service.git_discard(container_id)
            if not discard_result.get("success"):
                raise HTTPException(status_code=500, detail=discard_result.get("error", "Failed to discard changes"))
        else:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Uncommitted changes detected",
                    "files": uncommitted.get("files", []),
                },
            )

    result = git_service.git_pull(container_id, request.branch, token=token)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to pull"))

    return result


@router.get("/{workspace_id}/external-commits")
def external_commits(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    service = ExternalCommitService(supabase=supabase)
    result = service.check_external_commits(workspace_id, user_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to check external commits"))
    return result


@router.post("/{workspace_id}/reset-external")
def reset_external_commits(
    workspace_id: str,
    request: ResetExternalRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    service = ExternalCommitService(supabase=supabase)
    result = service.reset_to_platform_commit(workspace_id, user_id, request.confirmed)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to reset external commits"))
    return result


@router.get("/{workspace_id}/commits")
def list_commits(
    workspace_id: str,
    range_spec: Optional[str] = Query(default=None),
    max_count: int = Query(default=50, ge=1, le=200),
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
        container_id = _get_container_id(workspace_id, user_id, workspace_manager)
        git_service = GitService()

        result = git_service.git_log(container_id, range_spec=range_spec, max_count=max_count)
        if not result.get("success"):
            logger.error(f"Failed to get commits for workspace {workspace_id}: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get commits"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting commits for workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get commits: {str(e)}")
