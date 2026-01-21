"""
Docker Client Service
Wrapper around the Docker SDK for container operations.
"""

import logging
import socket
import threading

from docker.errors import APIError, ImageNotFound, NotFound

import docker

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
            raise RuntimeError(f"Docker is not available: {e}") from e

    def _get_client(self) -> docker.DockerClient:
        """Get a fresh Docker client for thread-safe operations."""
        return docker.from_env()

    def create_container(
        self,
        name: str,
        volume_name: str | None = None,
        image: str = DEFAULT_IMAGE,
        memory_limit: str = DEFAULT_MEMORY_LIMIT,
        cpu_quota: int = DEFAULT_CPU_QUOTA,
        ports: dict[str, tuple[str, int]] | None = None,
    ) -> tuple[str, str]:
        """
        Create a new container with resource limits and optional persistent volume.

        Args:
            name: Unique container name
            volume_name: Optional Docker volume name for /workspace persistence
            image: Docker image to use
            memory_limit: Memory limit (e.g., "512m")
            cpu_quota: CPU quota (50000 = 0.5 cores)
            ports: Optional port mappings dict, e.g., {'3000/tcp': ('0.0.0.0', 3000)}

        Returns:
            Tuple of (container_id, status)
        """
        try:
            client = self._get_client()

            # Create volume mount if volume_name provided
            volumes = None
            if volume_name:
                # Ensure volume exists
                self.create_volume(volume_name)
                volumes = {volume_name: {"bind": "/workspace", "mode": "rw"}}
                logger.info(f"Mounting volume {volume_name} to /workspace")

            # Prepare port bindings for high-level API
            # Format: {'container_port/tcp': host_port} e.g., {'3000/tcp': 30001}
            port_bindings = None
            if ports:
                port_bindings = {}
                for container_port, (host_ip, host_port) in ports.items():
                    # High-level API format: {'3000/tcp': ('0.0.0.0', 30001)} or {'3000/tcp': 30001}
                    port_bindings[container_port] = (host_ip, host_port)
                logger.info(f"Port mappings: {port_bindings}")

            # Use high-level API - more reliable for port mapping
            container = client.containers.create(
                image=image,
                name=name,
                detach=True,
                working_dir="/workspace",
                volumes=volumes,
                ports=port_bindings,
                mem_limit=memory_limit,
                cpu_period=DEFAULT_CPU_PERIOD,
                cpu_quota=cpu_quota,
                network_mode="bridge",
            )

            logger.info(f"Container created: {name} ({container.short_id})")
            return container.id, "created"
        except ImageNotFound as e:
            logger.error(f"Image not found: {image}")
            raise ValueError(f"Docker image not found: {image}") from e
        except APIError as e:
            logger.error(f"Failed to create container {name}: {e}")
            raise RuntimeError(f"Failed to create container: {e}") from e

    def start_container(self, container_id: str) -> tuple[bool, bool]:
        """
        Start a stopped container.

        Args:
            container_id: Container ID or name

        Returns:
            Tuple of (success, is_port_conflict)
        """
        try:
            client = self._get_client()
            container = client.containers.get(container_id)

            # Check current status
            container.reload()
            current_status = container.status
            logger.info(f"Container {container_id[:12]} current status: {current_status}")

            if current_status == "running":
                logger.info(f"Container {container_id[:12]} already running")
                return True, False

            # Start the container
            container.start()
            logger.info(f"Container started: {container_id}")
            return True, False
        except NotFound:
            logger.error(f"Container not found: {container_id}")
            return False, False
        except APIError as e:
            error_msg = str(e)
            # Check if error is due to port already in use
            is_port_conflict = "port is already allocated" in error_msg or (
                "bind:" in error_msg and "Only one usage" in error_msg
            )
            if is_port_conflict:
                logger.error(
                    f"Port conflict when starting container {container_id[:12]}: {error_msg}. "
                    f"Port is already in use. Consider using dynamic port allocation or stopping the conflicting service."
                )
            else:
                logger.error(f"Failed to start container {container_id}: {e}", exc_info=True)
            return False, is_port_conflict
        except Exception as e:
            logger.error(f"Unexpected error starting container {container_id}: {e}", exc_info=True)
            return False, False

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

    def get_container_ports(self, container_id: str) -> dict[str, list[dict[str, str]]]:
        """
        Get port mappings for a container.

        Args:
            container_id: Container ID or name

        Returns:
            Dict mapping container ports to host bindings, e.g.:
            {'3000/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '3000'}]}
        """
        try:
            client = self._get_client()
            container = client.containers.get(container_id)
            container.reload()
            return container.attrs.get("NetworkSettings", {}).get("Ports", {})
        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            return {}
        except APIError as e:
            logger.error(f"Failed to get ports for {container_id}: {e}")
            return {}

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
        self, container_id: str, command: str, workdir: str | None = None, retries: int = 2
    ) -> tuple[int, str]:
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
                    logger.error(
                        f"Container {container_id} is not running (status: {container.status})"
                    )
                    return -1, f"Container is not running (status: {container.status})"

                logger.debug(f"Executing command in {container_id[:12]}: {command[:50]}...")

                exec_result = container.exec_run(
                    cmd=["bash", "-c", command],
                    workdir=workdir or "/workspace",
                    demux=False,
                    tty=False,
                )

                output = exec_result.output.decode("utf-8") if exec_result.output else ""

                logger.debug(
                    f"Command exit code: {exec_result.exit_code}, output length: {len(output)}"
                )

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

    def create_volume(self, volume_name: str) -> bool:
        """
        Create a Docker volume if it doesn't exist.

        Args:
            volume_name: Name for the volume

        Returns:
            True if volume exists or was created successfully

        # ------------------------------------------------------------------
        # GCP DEPLOYMENT: Single VM with Docker (No code changes needed)
        # ------------------------------------------------------------------
        # This code works as-is on a GCP Compute Engine VM:
        #
        # Setup:
        #   1. Create e2-small VM (Ubuntu 22.04, 30GB disk)
        #   2. Install Docker: sudo apt install docker.io -y
        #   3. Docker volumes stored in /var/lib/docker/volumes/
        #   4. VM's persistent disk preserves volumes across reboots
        #
        # Data safety:
        #   - Container restarts: volumes persist
        #   - Docker restarts: volumes persist
        #   - VM reboots: volumes persist (on persistent disk)
        #   - VM deletion: data lost (avoid deleting the VM)
        #
        # Cost: ~$15-18/month, $300 credits last 16+ months
        # ------------------------------------------------------------------
        """
        try:
            client = self._get_client()

            # Check if volume already exists
            try:
                client.volumes.get(volume_name)
                logger.debug(f"Volume already exists: {volume_name}")
                return True
            except NotFound:
                pass

            # Create volume
            client.volumes.create(
                name=volume_name, driver="local", labels={"app": "gitguide", "type": "workspace"}
            )
            logger.info(f"Volume created: {volume_name}")
            return True
        except APIError as e:
            logger.error(f"Failed to create volume {volume_name}: {e}")
            return False

    def remove_volume(self, volume_name: str, force: bool = False) -> bool:
        """
        Remove a Docker volume.

        Args:
            volume_name: Name of the volume to remove
            force: Force removal even if in use

        Returns:
            True if removed successfully

        # ------------------------------------------------------------------
        # GCP DEPLOYMENT: Works as-is on Compute Engine VM
        # ------------------------------------------------------------------
        # Docker volumes on VM are removed with this same code.
        # No changes needed for single-VM deployment.
        # ------------------------------------------------------------------
        """
        try:
            client = self._get_client()
            volume = client.volumes.get(volume_name)
            volume.remove(force=force)
            logger.info(f"Volume removed: {volume_name}")
            return True
        except NotFound:
            logger.warning(f"Volume not found: {volume_name}")
            return True  # Already gone
        except APIError as e:
            logger.error(f"Failed to remove volume {volume_name}: {e}")
            return False

    def volume_exists(self, volume_name: str) -> bool:
        """
        Check if a Docker volume exists.

        Args:
            volume_name: Name of the volume

        Returns:
            True if volume exists
        """
        try:
            client = self._get_client()
            client.volumes.get(volume_name)
            return True
        except NotFound:
            return False

    def is_port_available(self, port: int, host: str = "0.0.0.0") -> bool:
        """
        Check if a port is available for binding.
        Checks both system-level port availability and Docker port bindings.

        Args:
            port: Port number to check
            host: Host IP address (default: 0.0.0.0)

        Returns:
            True if port is available
        """
        # Check system-level port availability
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
        except OSError:
            return False

        # Check if Docker is using this port
        try:
            client = self._get_client()
            containers = client.containers.list(all=True)
            for container in containers:
                container.reload()
                # Check HostConfig.PortBindings (configured ports)
                host_config_ports = container.attrs.get("HostConfig", {}).get("PortBindings", {})
                for _container_port, bindings in host_config_ports.items():
                    if bindings:
                        for binding in bindings:
                            if binding.get("HostPort") == str(port):
                                logger.debug(
                                    f"Port {port} is bound in HostConfig of container {container.id[:12]}"
                                )
                                return False

                # Check NetworkSettings.Ports (actual bound ports)
                network_ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
                for _container_port, bindings in network_ports.items():
                    if bindings:
                        for binding in bindings:
                            if binding.get("HostPort") == str(port):
                                logger.debug(
                                    f"Port {port} is bound in NetworkSettings of container {container.id[:12]}"
                                )
                                return False
        except Exception as e:
            logger.debug(f"Error checking Docker port bindings: {e}")
            # If we can't check Docker bindings, assume port is available
            # Docker will fail if it's actually in use

        return True

    def find_available_port(self, start_port: int, end_port: int = None, host: str = "0.0.0.0"):
        """
        Find an available port in the given range.

        Args:
            start_port: Starting port number
            end_port: Ending port number (default: start_port + 1000)
            host: Host IP address (default: 0.0.0.0)

        Returns:
            Available port number or None if none found
        """
        if end_port is None:
            end_port = start_port + 1000

        for port in range(start_port, end_port + 1):
            if self.is_port_available(port, host):
                logger.debug(f"Found available port: {port}")
                return port
            else:
                logger.debug(f"Port {port} is not available, trying next...")
        logger.warning(f"No available port found in range {start_port}-{end_port}")
        return None

    def check_port_conflict_error(self, error: Exception) -> bool:
        """
        Check if an error is due to a port conflict.

        Args:
            error: Exception to check

        Returns:
            True if error is a port conflict
        """
        error_msg = str(error)
        return "port is already allocated" in error_msg or (
            "bind:" in error_msg and "Only one usage" in error_msg
        )


# Singleton instance
_docker_client: DockerClient | None = None
_docker_client_lock = threading.Lock()


def get_docker_client() -> DockerClient:
    """Get or create the Docker client singleton (thread-safe)."""
    global _docker_client
    if _docker_client is None:
        with _docker_client_lock:
            if _docker_client is None:
                _docker_client = DockerClient()
    return _docker_client
