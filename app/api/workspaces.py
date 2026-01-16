"""
Workspace API Router
REST endpoints for Docker workspace management.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.external_commit_service import ExternalCommitService
from app.services.workspace_manager import Workspace, get_workspace_manager
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import get_user_id_from_clerk

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateWorkspaceRequest(BaseModel):
    project_id: str


class WorkspaceResponse(BaseModel):
    workspace_id: str
    user_id: str
    project_id: str
    container_id: str | None
    container_status: str
    created_at: str
    last_active_at: str


class CloneRepoResponse(BaseModel):
    success: bool
    status: str | None = None
    branch: str | None = None
    last_platform_commit: str | None = None
    error: str | None = None


def _workspace_to_response(ws: Workspace) -> WorkspaceResponse:
    """Convert Workspace dataclass to response model."""
    return WorkspaceResponse(
        workspace_id=ws.workspace_id,
        user_id=ws.user_id,
        project_id=ws.project_id,
        container_id=ws.container_id,
        container_status=ws.container_status,
        created_at=ws.created_at.isoformat(),
        last_active_at=ws.last_active_at.isoformat(),
    )


@router.post("/create")
async def create_workspace(
    request: CreateWorkspaceRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Create a new workspace for a project.
    If workspace already exists for this user+project, returns the existing one.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        logger.info(f"Creating workspace for user={user_id}, project={request.project_id}")

        manager = get_workspace_manager()
        workspace = manager.get_or_create_workspace(user_id, request.project_id)

        git_result = None
        try:
            git_result = manager.initialize_git_repo(
                workspace.workspace_id,
                user_id,
                author_name=user_info.get("name") or "GitGuide",
                author_email=user_info.get("email") or "noreply@gitguide.local",
            )
        except Exception as e:
            logger.warning(f"Git init skipped: {e}")

        # Check external commits and auto-reset if consented
        if git_result and git_result.get("success"):
            try:
                external_service = ExternalCommitService(supabase=supabase)
                external = external_service.check_external_commits(workspace.workspace_id, user_id)
                if external.get("success") and external.get("has_external_commits"):
                    external_service.reset_to_platform_commit(
                        workspace.workspace_id,
                        user_id,
                        confirmed=True,
                    )
            except Exception as e:
                logger.warning(f"External commit check skipped: {e}")

        return {
            "success": True,
            "workspace": _workspace_to_response(workspace),
            "git": git_result,
        }

    except ValueError as e:
        logger.error(f"Validation error creating workspace: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        logger.error(f"Runtime error creating workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error creating workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create workspace: {str(e)}") from e


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get workspace details by ID.
    """
    try:
        logger.debug(f"[API_GET_WORKSPACE] Request for workspace: {workspace_id}")
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)
        logger.debug(f"[API_GET_WORKSPACE] User: {user_id}")

        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            logger.warning(f"[API_GET_WORKSPACE] Workspace not found: {workspace_id}")
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify ownership
        if workspace.user_id != user_id:
            logger.warning(
                f"[API_GET_WORKSPACE] Access denied for user {user_id} on workspace {workspace_id}"
            )
            raise HTTPException(status_code=403, detail="Access denied")

        logger.debug(
            f"[API_GET_WORKSPACE] Returning workspace: {workspace_id}, status: {workspace.container_status}"
        )
        return {
            "success": True,
            "workspace": _workspace_to_response(workspace),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch workspace: {str(e)}") from e


@router.get("/project/{project_id}")
async def get_workspace_by_project(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get workspace for a specific project.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        workspace = manager.get_workspace_by_user_project(user_id, project_id)

        if not workspace:
            raise HTTPException(status_code=404, detail="No workspace found for this project")

        return {
            "success": True,
            "workspace": _workspace_to_response(workspace),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch workspace: {str(e)}") from e


@router.delete("/{workspace_id}")
async def destroy_workspace(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Destroy a workspace - stops and removes the container, deletes from database.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify ownership
        if workspace.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        success = manager.destroy_workspace(workspace_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to destroy workspace")

        return {
            "success": True,
            "message": "Workspace destroyed successfully",
            "workspace_id": workspace_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error destroying workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to destroy workspace: {str(e)}") from e


@router.post("/{workspace_id}/start")
async def start_workspace(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Start a stopped workspace container.
    """
    try:
        logger.info(f"[API_START] Request to start workspace: {workspace_id}")
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            logger.warning(f"[API_START] Workspace not found: {workspace_id}")
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify ownership
        if workspace.user_id != user_id:
            logger.warning(f"[API_START] Access denied for user {user_id}")
            raise HTTPException(status_code=403, detail="Access denied")

        logger.debug(f"[API_START] Current status: {workspace.container_status}")
        success = manager.start_workspace(workspace_id)

        if not success:
            logger.error(f"[API_START] Failed to start workspace: {workspace_id}")
            raise HTTPException(status_code=500, detail="Failed to start workspace")

        # Attempt to initialize git repo if ready
        git_result = None
        try:
            git_result = manager.initialize_git_repo(
                workspace_id,
                user_id,
                author_name=user_info.get("name") or "GitGuide",
                author_email=user_info.get("email") or "noreply@gitguide.local",
            )
        except Exception as e:
            logger.warning(f"Git init skipped on start: {e}")

        # Check for external commits and auto-reset if consented
        external_result = None
        try:
            external_service = ExternalCommitService(supabase=supabase)
            external_result = external_service.check_external_commits(workspace_id, user_id)
            if external_result.get("has_external_commits"):
                reset_result = external_service.reset_to_platform_commit(
                    workspace_id, user_id, confirmed=True
                )
                external_result["auto_reset"] = reset_result
        except Exception as e:
            logger.warning(f"External commit check skipped: {e}")

        logger.info(f"[API_START] Workspace started: {workspace_id}")
        return {
            "success": True,
            "message": "Workspace started successfully",
            "workspace_id": workspace_id,
            "status": "running",
            "git": git_result,
            "external_commits": external_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start workspace: {str(e)}") from e


@router.post("/{workspace_id}/stop")
async def stop_workspace(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Stop a running workspace container.
    """
    try:
        logger.info(f"[API_STOP] Request to stop workspace: {workspace_id}")
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            logger.warning(f"[API_STOP] Workspace not found: {workspace_id}")
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify ownership
        if workspace.user_id != user_id:
            logger.warning(f"[API_STOP] Access denied for user {user_id}")
            raise HTTPException(status_code=403, detail="Access denied")

        logger.debug(f"[API_STOP] Current status: {workspace.container_status}")
        success = manager.stop_workspace(workspace_id)

        if not success:
            logger.error(f"[API_STOP] Failed to stop workspace: {workspace_id}")
            raise HTTPException(status_code=500, detail="Failed to stop workspace")

        logger.info(f"[API_STOP] Workspace stopped: {workspace_id}")
        return {
            "success": True,
            "message": "Workspace stopped successfully",
            "workspace_id": workspace_id,
            "status": "exited",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop workspace: {str(e)}") from e


@router.post("/{workspace_id}/clone-repo", response_model=CloneRepoResponse)
async def clone_repo(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Clone user's repository into the workspace and configure git.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        result = manager.initialize_git_repo(
            workspace_id,
            user_id,
            author_name=user_info.get("name") or "GitGuide",
            author_email=user_info.get("email") or "noreply@gitguide.local",
        )

        if not result.get("success"):
            return CloneRepoResponse(success=False, error=result.get("error"))

        return CloneRepoResponse(
            success=True,
            status=result.get("status"),
            branch=result.get("branch"),
            last_platform_commit=result.get("last_platform_commit"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cloning repo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to clone repo: {str(e)}") from e


@router.get("/{workspace_id}/status")
async def get_workspace_status(
    workspace_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get the current container status for a workspace.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify ownership
        if workspace.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        status = manager.get_workspace_status(workspace_id)

        return {
            "success": True,
            "workspace_id": workspace_id,
            "status": status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch status: {str(e)}") from e
