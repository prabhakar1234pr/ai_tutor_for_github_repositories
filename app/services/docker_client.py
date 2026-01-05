"""
Docker Client Service
Wrapper around the Docker SDK for container operations.
"""

import docker
from docker.errors import NotFound, APIError, ImageNotFound
from typing import Optional, Tuple
import logging
import threading

logger = logging.getLogger(__name__)

# Default resource limits for workspace containers
DEFAULT_MEMORY_LIMIT = "512m"
DEFAULT_CPU_PERIOD = 100000
DEFAULT_CPU_QUOTA = 50000  # 0.5 CPU cores
DEFAULT_IMAGE = "gitguide-workspace:latest"


class DockerClient:
    """
    Thread-safe wrapper for Docker SDK operations on workspace containers.
    
    Creates a fresh Docker client for each operation to avoid connection issues
    in multi-threaded environments like FastAPI.
    """

    _lock = threading.Lock()

    def __init__(self):
        """Initialize Docker client - verify connection is available."""
        try:
            client = docker.from_env()
            client.ping()
            logger.info("Docker client initialized - connection verified")
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise RuntimeError(f"Docker is not available: {e}")

    def _get_client(self) -> docker.DockerClient:
        """Get a fresh Docker client for thread-safe operations."""
        return docker.from_env()

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
            client = self._get_client()
            container = client.containers.create(
                image=image,
                name=name,
                detach=True,
                mem_limit=memory_limit,
                cpu_period=DEFAULT_CPU_PERIOD,
                cpu_quota=cpu_quota,
                privileged=False,
                network_mode="bridge",
                working_dir="/workspace",
                tty=True,  # Keep container alive and enable proper exec
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
            client = self._get_client()
            container = client.containers.get(container_id)
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
            client = self._get_client()
            container = client.containers.get(container_id)
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
            client = self._get_client()
            container = client.containers.get(container_id)
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
            client = self._get_client()
            container = client.containers.get(container_id)
            # Reload to get fresh status
            container.reload()
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
            client = self._get_client()
            client.containers.get(container_id)
            return True
        except NotFound:
            return False

    def exec_command(
        self, container_id: str, command: str, workdir: Optional[str] = None, retries: int = 2
    ) -> Tuple[int, str]:
        """
        Execute a command inside a running container.

        Args:
            container_id: Container ID or name
            command: Command to execute
            workdir: Working directory (optional)
            retries: Number of retry attempts for transient failures

        Returns:
            Tuple of (exit_code, output)
        """
        last_error = None
        
        for attempt in range(retries + 1):
            try:
                client = self._get_client()
                container = client.containers.get(container_id)
                
                # Reload to get fresh status
                container.reload()

                if container.status != "running":
                    logger.error(f"Container {container_id} is not running (status: {container.status})")
                    return -1, f"Container is not running (status: {container.status})"

                logger.debug(f"Executing command in {container_id[:12]}: {command[:50]}...")
                
                exec_result = container.exec_run(
                    cmd=["bash", "-c", command],
                    workdir=workdir or "/workspace",
                    demux=False,
                    tty=False,
                )

                output = exec_result.output.decode("utf-8") if exec_result.output else ""
                
                logger.debug(f"Command exit code: {exec_result.exit_code}, output length: {len(output)}")
                
                return exec_result.exit_code, output

            except NotFound:
                logger.error(f"Container not found: {container_id}")
                return -1, "Container not found"
            except APIError as e:
                last_error = str(e)
                logger.warning(f"Exec attempt {attempt + 1} failed for {container_id}: {e}")
                if attempt < retries:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Brief backoff
                    continue
                logger.error(f"Failed to exec in {container_id} after {retries + 1} attempts: {e}")
                return -1, str(e)
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error in exec_command: {e}")
                if attempt < retries:
                    import time
                    time.sleep(0.1 * (attempt + 1))
                    continue
                return -1, str(e)
        
        return -1, last_error or "Unknown error"

    def is_docker_available(self) -> bool:
        """Check if Docker daemon is available."""
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception:
            return False


# Singleton instance
_docker_client: Optional[DockerClient] = None
_docker_client_lock = threading.Lock()


def get_docker_client() -> DockerClient:
    """Get or create the Docker client singleton (thread-safe)."""
    global _docker_client
    if _docker_client is None:
        with _docker_client_lock:
            if _docker_client is None:
                _docker_client = DockerClient()
    return _docker_client
