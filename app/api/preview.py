"""
Preview Proxy API Router
Proxies HTTP requests to development servers running in workspace containers.

This enables students to preview their web apps after GCP deployment.
Locally, they can use direct port access (localhost:30001-30010).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.preview_proxy import get_preview_proxy
from app.services.workspace_manager import get_workspace_manager
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import get_user_id_from_clerk

router = APIRouter()
logger = logging.getLogger(__name__)


@router.api_route(
    "/{workspace_id}/{port:int}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_preview(
    workspace_id: str,
    port: int,
    path: str,
    request: Request,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Proxy requests to development servers running in workspace containers.

    Example:
        GET /api/preview/{workspace_id}/3000/api/data
        → Proxies to container's port 3000 at /api/data
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        # Verify workspace ownership
        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        if workspace.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        if workspace.container_status != "running":
            raise HTTPException(
                status_code=400,
                detail=f"Container not running (status: {workspace.container_status})",
            )

        # Get request body if present
        body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None

        # Convert headers to dict
        headers = dict(request.headers)

        # Ensure path starts with /
        proxy_path = f"/{path}" if not path.startswith("/") else path

        # Add query string if present
        if request.query_params:
            proxy_path += f"?{request.query_params}"

        # Proxy the request
        proxy = get_preview_proxy()
        status_code, response_headers, response_body = await proxy.proxy_request(
            workspace_id=workspace_id,
            container_port=port,
            path=proxy_path,
            method=request.method,
            headers=headers,
            body=body,
        )

        return Response(
            content=response_body,
            status_code=status_code,
            headers=response_headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview proxy error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}") from e


@router.get("/{workspace_id}/info")
async def get_preview_info(
    workspace_id: str,
    request: Request,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Get preview URLs and port information for a workspace.

    Returns URLs appropriate for the deployment environment:
    - Local: localhost:30001, localhost:30002, etc.
    - GCP: Proxy URLs through the backend
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        # Verify workspace ownership
        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        if workspace.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Determine base URL for proxy
        # In production, use the request's base URL
        # Locally, return None to get direct localhost URLs
        base_url = None

        # Check if we're behind a proxy or in production
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto", "https")

        if forwarded_host:
            # Production/GCP - use proxy URLs
            base_url = f"{forwarded_proto}://{forwarded_host}"
        elif request.base_url.hostname not in ["localhost", "127.0.0.1"]:
            # Direct production access
            base_url = str(request.base_url).rstrip("/")
        # else: local development - base_url stays None for direct access

        proxy = get_preview_proxy()
        preview_info = proxy.get_preview_urls(
            workspace_id=workspace_id,
            container_id=workspace.container_id,
            base_url=base_url,
        )

        return {
            "success": True,
            "workspace_id": workspace_id,
            "container_status": workspace.container_status,
            "preview": preview_info,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preview info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get preview info: {str(e)}") from e


@router.get("/{workspace_id}/servers")
async def list_detected_servers(
    workspace_id: str,
    request: Request,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    List detected dev servers and their preview URLs for a workspace.
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        user_id = get_user_id_from_clerk(supabase, clerk_user_id)

        manager = get_workspace_manager()
        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        if workspace.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Determine base URL for proxy
        base_url = None
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto", "https")

        if forwarded_host:
            base_url = f"{forwarded_proto}://{forwarded_host}"
        elif request.base_url.hostname not in ["localhost", "127.0.0.1"]:
            base_url = str(request.base_url).rstrip("/")

        proxy = get_preview_proxy()
        servers = proxy.get_detected_servers(workspace_id)
        formatted_servers = []

        for server in servers:
            port = server.get("detected_port")
            if not port or not workspace.container_id:
                continue
            url, url_type, host_port = proxy.build_preview_url(
                workspace_id=workspace_id,
                container_id=workspace.container_id,
                container_port=int(port),
                base_url=base_url,
            )
            formatted_servers.append(
                {
                    "container_port": int(port),
                    "host_port": host_port,
                    "url": url,
                    "type": url_type,
                    "server_type": server.get("server_type"),
                    "detected_at": server.get("detected_at"),
                    "is_active": server.get("is_active", True),
                }
            )

        return {
            "success": True,
            "workspace_id": workspace_id,
            "servers": formatted_servers,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing detected servers: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list detected servers: {str(e)}"
        ) from e
