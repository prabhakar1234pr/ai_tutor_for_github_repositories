"""
Workspace API Router
REST endpoints for Docker workspace management.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from supabase import Client
import logging

from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import get_user_id_from_clerk
from app.services.workspace_manager import get_workspace_manager, Workspace

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

        return {
            "success": True,
            "workspace": _workspace_to_response(workspace),
        }

    except ValueError as e:
        logger.error(f"Validation error creating workspace: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Runtime error creating workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create workspace: {str(e)}")


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
            logger.warning(f"[API_GET_WORKSPACE] Access denied for user {user_id} on workspace {workspace_id}")
            raise HTTPException(status_code=403, detail="Access denied")

        logger.debug(f"[API_GET_WORKSPACE] Returning workspace: {workspace_id}, status: {workspace.container_status}")
        return {
            "success": True,
            "workspace": _workspace_to_response(workspace),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch workspace: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to fetch workspace: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to destroy workspace: {str(e)}")


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

        logger.info(f"[API_START] Workspace started: {workspace_id}")
        return {
            "success": True,
            "message": "Workspace started successfully",
            "workspace_id": workspace_id,
            "status": "running",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start workspace: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to stop workspace: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to fetch status: {str(e)}")

