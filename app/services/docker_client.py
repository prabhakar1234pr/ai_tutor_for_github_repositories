"""
Docker Client Service
Wrapper around the Docker SDK for container operations.
"""

import docker
from docker.errors import NotFound, APIError, ImageNotFound
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Default resource limits for workspace containers
DEFAULT_MEMORY_LIMIT = "512m"
DEFAULT_CPU_PERIOD = 100000
DEFAULT_CPU_QUOTA = 50000  # 0.5 CPU cores
DEFAULT_IMAGE = "gitguide-workspace:latest"


class DockerClient:
    """Wrapper for Docker SDK operations on workspace containers."""

    def __init__(self):
        """Initialize Docker client connection."""
        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Docker client connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise RuntimeError(f"Docker is not available: {e}")

    def create_container(
        self,
        name: str,
        image: str = DEFAULT_IMAGE,
        memory_limit: str = DEFAULT_MEMORY_LIMIT,
        cpu_quota: int = DEFAULT_CPU_QUOTA,
    ) -> Tuple[str, str]:
        """
        Create a new container with resource limits.

        Args:
            name: Unique container name
            image: Docker image to use
            memory_limit: Memory limit (e.g., "512m")
            cpu_quota: CPU quota (50000 = 0.5 cores)

        Returns:
            Tuple of (container_id, status)
        """
        try:
            container = self.client.containers.create(
                image=image,
                name=name,
                detach=True,
                mem_limit=memory_limit,
                cpu_period=DEFAULT_CPU_PERIOD,
                cpu_quota=cpu_quota,
                privileged=False,
                network_mode="bridge",
                working_dir="/workspace",
            )
            logger.info(f"Container created: {name} ({container.short_id})")
            return container.id, "created"
        except ImageNotFound:
            logger.error(f"Image not found: {image}")
            raise ValueError(f"Docker image not found: {image}")
        except APIError as e:
            logger.error(f"Failed to create container {name}: {e}")
            raise RuntimeError(f"Failed to create container: {e}")

    def start_container(self, container_id: str) -> bool:
        """
        Start a stopped container.

        Args:
            container_id: Container ID or name

        Returns:
            True if started successfully
        """
        try:
            container = self.client.containers.get(container_id)
            container.start()
            logger.info(f"Container started: {container_id}")
            return True
        except NotFound:
            logger.error(f"Container not found: {container_id}")
            return False
        except APIError as e:
            logger.error(f"Failed to start container {container_id}: {e}")
            return False

    def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """
        Stop a running container.

        Args:
            container_id: Container ID or name
            timeout: Seconds to wait before killing

        Returns:
            True if stopped successfully
        """
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
            logger.info(f"Container stopped: {container_id}")
            return True
        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            return True  # Already gone
        except APIError as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            return False

    def remove_container(self, container_id: str, force: bool = True) -> bool:
        """
        Remove a container.

        Args:
            container_id: Container ID or name
            force: Force removal even if running

        Returns:
            True if removed successfully
        """
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            logger.info(f"Container removed: {container_id}")
            return True
        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            return True  # Already gone
        except APIError as e:
            logger.error(f"Failed to remove container {container_id}: {e}")
            return False

    def get_container_status(self, container_id: str) -> str:
        """
        Get the current status of a container.

        Args:
            container_id: Container ID or name

        Returns:
            Status string: "running", "exited", "created", "paused", or "not_found"
        """
        try:
            container = self.client.containers.get(container_id)
            return container.status
        except NotFound:
            return "not_found"
        except APIError as e:
            logger.error(f"Failed to get status for {container_id}: {e}")
            return "error"

    def container_exists(self, container_id: str) -> bool:
        """
        Check if a container exists.

        Args:
            container_id: Container ID or name

        Returns:
            True if container exists
        """
        try:
            self.client.containers.get(container_id)
            return True
        except NotFound:
            return False

    def exec_command(
        self, container_id: str, command: str, workdir: Optional[str] = None
    ) -> Tuple[int, str]:
        """
        Execute a command inside a running container.

        Args:
            container_id: Container ID or name
            command: Command to execute
            workdir: Working directory (optional)

        Returns:
            Tuple of (exit_code, output)
        """
        try:
            container = self.client.containers.get(container_id)

            if container.status != "running":
                logger.error(f"Container {container_id} is not running")
                return -1, "Container is not running"

            exec_result = container.exec_run(
                cmd=["bash", "-c", command],
                workdir=workdir or "/workspace",
                demux=False,
            )

            output = exec_result.output.decode("utf-8") if exec_result.output else ""
            return exec_result.exit_code, output

        except NotFound:
            logger.error(f"Container not found: {container_id}")
            return -1, "Container not found"
        except APIError as e:
            logger.error(f"Failed to exec in {container_id}: {e}")
            return -1, str(e)

    def is_docker_available(self) -> bool:
        """Check if Docker daemon is available."""
        try:
            self.client.ping()
            return True
        except Exception:
            return False


# Singleton instance
_docker_client: Optional[DockerClient] = None


def get_docker_client() -> DockerClient:
    """Get or create the Docker client singleton."""
    global _docker_client
    if _docker_client is None:
        _docker_client = DockerClient()
    return _docker_client

