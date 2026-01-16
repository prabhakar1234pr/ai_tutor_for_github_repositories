"""
File System API Router
REST endpoints for file operations inside workspace containers.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.file_system import FileSystemService, get_file_system_service
from app.services.workspace_manager import WorkspaceManager, get_workspace_manager
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import get_user_id_from_clerk

router = APIRouter()
logger = logging.getLogger(__name__)


# Request/Response Models


class FileItem(BaseModel):
    name: str
    path: str
    is_directory: bool
    size: int
    permissions: str


class ListFilesResponse(BaseModel):
    success: bool
    path: str
    files: list[FileItem]


class ReadFileResponse(BaseModel):
    success: bool
    path: str
    content: str


class WriteFileRequest(BaseModel):
    path: str
    content: str


class CreateFileRequest(BaseModel):
    path: str
    is_directory: bool = False


class DeleteFileRequest(BaseModel):
    path: str


class RenameFileRequest(BaseModel):
    old_path: str
    new_path: str


# Helper to get container_id from workspace


def get_container_id(workspace_id: str, user_id: str, workspace_manager: WorkspaceManager) -> str:
    """Get container ID for a workspace, verifying ownership."""
    workspace = workspace_manager.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this workspace")

    container_id = workspace.container_id
    if not container_id:
        raise HTTPException(status_code=400, detail="Workspace has no container")

    # Check container is running
    status = workspace.container_status
    if status != "running":
        raise HTTPException(
            status_code=400, detail=f"Workspace container is not running (status: {status})"
        )

    return container_id


# Endpoints


@router.get("/{workspace_id}/files", response_model=ListFilesResponse)
def list_files(
    workspace_id: str,
    path: str = Query(default="/workspace", description="Directory path to list"),
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    file_system: FileSystemService = Depends(get_file_system_service),
):
    """List files and directories at the given path."""
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
        container_id = get_container_id(workspace_id, user_id, workspace_manager)

        files = file_system.list_files(container_id, path)

        return ListFilesResponse(
            success=True, path=path, files=[FileItem(**f.to_dict()) for f in files]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing files at {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


@router.get("/{workspace_id}/files/content", response_model=ReadFileResponse)
def read_file(
    workspace_id: str,
    path: str = Query(..., description="File path to read"),
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    file_system: FileSystemService = Depends(get_file_system_service),
):
    """Read content of a file."""
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
        container_id = get_container_id(workspace_id, user_id, workspace_manager)

        content = file_system.read_file(container_id, path)

        if content is None:
            raise HTTPException(status_code=404, detail=f"File not found or not readable: {path}")

        return ReadFileResponse(success=True, path=path, content=content)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error reading file {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


@router.put("/{workspace_id}/files/content")
def write_file(
    workspace_id: str,
    request: WriteFileRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    file_system: FileSystemService = Depends(get_file_system_service),
):
    """Write content to a file."""
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
        container_id = get_container_id(workspace_id, user_id, workspace_manager)

        logger.info(f"Writing file: {request.path} ({len(request.content)} chars)")

        success = file_system.write_file(container_id, request.path, request.content)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to write file: {request.path}")

        return {"success": True, "message": "File saved successfully", "path": request.path}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error writing file {request.path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


@router.post("/{workspace_id}/files")
def create_file(
    workspace_id: str,
    request: CreateFileRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    file_system: FileSystemService = Depends(get_file_system_service),
):
    """Create a new file or directory."""
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])

        container_id = get_container_id(workspace_id, user_id, workspace_manager)

        logger.info(
            f"Creating {'directory' if request.is_directory else 'file'}: {request.path} in container {container_id[:12]}"
        )

        if request.is_directory:
            success = file_system.create_directory(container_id, request.path)
        else:
            success = file_system.create_file(container_id, request.path)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to create: {request.path}")

        return {
            "success": True,
            "message": f"{'Directory' if request.is_directory else 'File'} created successfully",
            "path": request.path,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating file {request.path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


@router.delete("/{workspace_id}/files")
def delete_file(
    workspace_id: str,
    path: str = Query(..., description="Path to delete"),
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    file_system: FileSystemService = Depends(get_file_system_service),
):
    """Delete a file or directory."""
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
        container_id = get_container_id(workspace_id, user_id, workspace_manager)

        success = file_system.delete_file(container_id, path)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete: {path}")

        return {"success": True, "message": "Deleted successfully", "path": path}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


@router.post("/{workspace_id}/files/rename")
def rename_file(
    workspace_id: str,
    request: RenameFileRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    file_system: FileSystemService = Depends(get_file_system_service),
):
    """Rename or move a file/directory."""
    try:
        user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
        container_id = get_container_id(workspace_id, user_id, workspace_manager)

        success = file_system.rename_file(container_id, request.old_path, request.new_path)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to rename: {request.old_path}")

        return {
            "success": True,
            "message": "Renamed successfully",
            "old_path": request.old_path,
            "new_path": request.new_path,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error renaming {request.old_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e
