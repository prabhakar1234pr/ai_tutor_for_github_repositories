"""
Preview Proxy Service
Proxies HTTP requests to development servers running inside workspace containers.

This enables students to preview their web apps:
- Locally: Direct access via localhost:30001-30003
- GCP Deployed: Access via /api/preview/{workspace_id}/{port}/path
"""

import logging
from typing import TYPE_CHECKING, Any

import httpx

from app.services.docker_client import get_docker_client

# Lazy imports to avoid circular dependency
if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Port mapping configuration
# Container port -> Host port (for local development)
# Use ports 30001-30010 to avoid conflicts with frontend (3000) and backend (8000)
PORT_MAPPING = {
    3000: 30001,  # React/Next.js/Vite dev servers
    5000: 30002,  # Flask default
    5173: 30003,  # Vite default
    4200: 30004,  # Angular default
    8080: 30005,  # Common alternative
    8888: 30006,  # Jupyter notebook
    4000: 30007,  # Various frameworks
    9000: 30008,  # PHP/other
    3001: 30009,  # Secondary dev server
    5500: 30010,  # Live Server extension
}

# Default ports to expose on containers
DEFAULT_CONTAINER_PORTS = list(PORT_MAPPING.keys())


class PreviewProxyService:
    """
    Handles proxying HTTP requests to development servers in containers.

    For local development:
        - Containers expose ports via Docker port mapping
        - Students access localhost:30001 for container port 3000

    For GCP deployment:
        - Backend proxies requests to container's internal network
        - Students access https://your-domain.com/api/preview/{workspace_id}/3000/path
    """

    def __init__(self):
        self._workspace_manager = None
        self.docker_client = get_docker_client()
        # HTTP client with reasonable timeouts for dev server responses
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=True,
        )

    @property
    def workspace_manager(self):
        """Lazy load workspace_manager to avoid circular import."""
        if self._workspace_manager is None:
            from app.services.workspace_manager import get_workspace_manager

            self._workspace_manager = get_workspace_manager()
        return self._workspace_manager

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()

    def get_container_ip(self, container_id: str) -> str | None:
        """
        Get the internal IP address of a container for proxying.

        Args:
            container_id: Docker container ID

        Returns:
            Container IP address or None if not found
        """
        try:
            import docker

            client = docker.from_env()
            container = client.containers.get(container_id)
            container.reload()

            # Get IP from bridge network
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            bridge = networks.get("bridge", {})
            ip = bridge.get("IPAddress")

            if ip:
                logger.debug(f"Container {container_id[:12]} IP: {ip}")
                return ip

            logger.warning(f"No IP found for container {container_id[:12]}")
            return None
        except Exception as e:
            logger.error(f"Failed to get container IP: {e}")
            return None

    def get_host_port(self, container_id: str, container_port: int) -> int | None:
        """
        Get the host port mapped to a container port.

        Args:
            container_id: Docker container ID
            container_port: Port inside the container

        Returns:
            Host port number or None if not mapped
        """
        try:
            port_mappings = self.docker_client.get_container_ports(container_id)
            port_key = f"{container_port}/tcp"

            bindings = port_mappings.get(port_key, [])
            if bindings:
                host_port = bindings[0].get("HostPort")
                if host_port:
                    return int(host_port)

            return None
        except Exception as e:
            logger.error(f"Failed to get host port: {e}")
            return None

    async def proxy_request(
        self,
        workspace_id: str,
        container_port: int,
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """
        Proxy an HTTP request to a container's dev server.

        Args:
            workspace_id: Workspace UUID
            container_port: Port inside the container (e.g., 3000)
            path: Request path (e.g., "/api/data")
            method: HTTP method
            headers: Request headers
            body: Request body

        Returns:
            Tuple of (status_code, response_headers, response_body)
        """
        workspace = self.workspace_manager.get_workspace(workspace_id)
        if not workspace:
            return 404, {"Content-Type": "application/json"}, b'{"error": "Workspace not found"}'

        if not workspace.container_id:
            return 404, {"Content-Type": "application/json"}, b'{"error": "No container"}'

        # Get container IP for internal proxying
        container_ip = self.get_container_ip(workspace.container_id)
        if not container_ip:
            return (
                502,
                {"Content-Type": "application/json"},
                b'{"error": "Container not reachable"}',
            )

        # Build target URL
        target_url = f"http://{container_ip}:{container_port}{path}"
        logger.debug(f"Proxying {method} {path} to {target_url}")

        # Filter headers (remove hop-by-hop headers)
        proxy_headers = {}
        if headers:
            skip_headers = {
                "host",
                "connection",
                "keep-alive",
                "transfer-encoding",
                "te",
                "trailer",
                "upgrade",
                "proxy-authorization",
                "proxy-authenticate",
            }
            proxy_headers = {k: v for k, v in headers.items() if k.lower() not in skip_headers}

        try:
            response = await self.http_client.request(
                method=method,
                url=target_url,
                headers=proxy_headers,
                content=body,
            )

            # Filter response headers
            response_headers = {}
            skip_response_headers = {"transfer-encoding", "connection", "keep-alive"}
            for name, value in response.headers.items():
                if name.lower() not in skip_response_headers:
                    response_headers[name] = value

            return response.status_code, response_headers, response.content

        except httpx.ConnectError:
            logger.warning(f"Connection refused to {target_url} - server may not be running")
            return (
                502,
                {"Content-Type": "application/json"},
                b'{"error": "Server not running. Start your dev server first (e.g., npm run dev)"}',
            )
        except httpx.TimeoutException:
            logger.warning(f"Timeout connecting to {target_url}")
            return 504, {"Content-Type": "application/json"}, b'{"error": "Server timeout"}'
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return 500, {"Content-Type": "application/json"}, b'{"error": "Proxy error"}'

    def get_preview_urls(
        self,
        workspace_id: str,
        container_id: str | None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Get preview URLs for all exposed ports.

        Args:
            workspace_id: Workspace UUID
            container_id: Docker container ID
            base_url: Base URL for proxy endpoints (e.g., "https://api.gitguide.com")
                     If None, returns localhost URLs for local development

        Returns:
            Dict with port info and URLs
        """
        preview_info = {
            "ports": {},
            "instructions": [],
        }

        if not container_id:
            preview_info["instructions"].append("No container - create workspace first")
            return preview_info

        # Get actual port mappings from container
        port_mappings = self.docker_client.get_container_ports(container_id)

        for container_port, _host_port in PORT_MAPPING.items():
            port_key = f"{container_port}/tcp"
            bindings = port_mappings.get(port_key, [])

            actual_host_port = None
            if bindings:
                actual_host_port = bindings[0].get("HostPort")

            port_info = {
                "container_port": container_port,
                "host_port": actual_host_port,
                "mapped": actual_host_port is not None,
            }

            if actual_host_port:
                if base_url:
                    # GCP/Production: Use proxy endpoint
                    port_info["url"] = f"{base_url}/api/preview/{workspace_id}/{container_port}/"
                    port_info["type"] = "proxy"
                else:
                    # Local: Direct access
                    port_info["url"] = f"http://localhost:{actual_host_port}"
                    port_info["type"] = "direct"

            preview_info["ports"][container_port] = port_info

        # Add helpful instructions
        if base_url:
            preview_info["instructions"].append(
                "Run your dev server (e.g., npm run dev) then access the preview URL"
            )
            preview_info["instructions"].append(
                "Make sure your server listens on 0.0.0.0 (not localhost/127.0.0.1)"
            )
        else:
            preview_info["instructions"].append(
                "For local development, access localhost URLs directly"
            )
            preview_info["instructions"].append("Example: npm run dev → localhost:30001")

        return preview_info


# Singleton instance
_preview_proxy: PreviewProxyService | None = None


def get_preview_proxy() -> PreviewProxyService:
    """Get or create the PreviewProxyService singleton."""
    global _preview_proxy
    if _preview_proxy is None:
        _preview_proxy = PreviewProxyService()
    return _preview_proxy
