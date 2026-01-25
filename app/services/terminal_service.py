"""
Terminal Service
Manages PTY sessions for interactive terminal access in Docker containers.
"""

import asyncio
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from docker.errors import APIError, NotFound

import docker
from app.core.supabase_client import get_supabase_client
from app.services.docker_client import get_docker_client
from app.services.git_service import GitService

logger = logging.getLogger(__name__)


@dataclass
class TerminalSession:
    """Terminal session data model."""

    session_id: str
    workspace_id: str
    exec_id: str
    name: str
    is_active: bool
    created_at: datetime


class TerminalService:
    """
    Manages PTY terminal sessions in Docker containers.

    Provides interactive shell access with bidirectional streaming
    and terminal resize support.
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.docker_client = get_docker_client()
        self.git_service = GitService()
        self.table_name = "terminal_sessions"
        # Active exec streams: session_id -> (socket, exec_id)
        self._active_streams: dict[str, Any] = {}
        # Output buffers for commit detection: session_id -> buffer_string
        self._output_buffers: dict[str, str] = {}
        # Maximum buffer size per session (keep last 10KB of output)
        self._max_buffer_size = 10240
        # Track last processed commit SHA per session to avoid duplicate updates
        self._last_processed_commits: dict[str, str] = {}
        # Track announced preview ports per session to avoid duplicate messages
        self._announced_ports: dict[str, set[int]] = {}
        # Patterns to detect dev server URLs/ports from terminal output
        self._preview_patterns = [
            re.compile(r"(?:Local|local):\s*https?://[^\s:]+:(\d{2,5})"),
            re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\]|::1):(\d{2,5})"),
            re.compile(
                r"(?:listening on|started on|server running at|running at)\s+"
                r"(?:https?://)?(?:0\.0\.0\.0|127\.0\.0\.1|localhost)?[:\s](\d{2,5})",
                re.IGNORECASE,
            ),
            re.compile(r"port\s+(\d{2,5})\s*(?:open|listening|ready)", re.IGNORECASE),
        ]

    def _row_to_session(self, row: dict) -> TerminalSession:
        """Convert database row to TerminalSession object."""
        return TerminalSession(
            session_id=row["session_id"],
            workspace_id=row["workspace_id"],
            exec_id=row.get("exec_id", ""),
            name=row.get("name", "Terminal"),
            is_active=row.get("is_active", True),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

    def create_session(
        self, workspace_id: str, container_id: str, name: str = "Terminal"
    ) -> TerminalSession:
        """
        Create a new terminal session for a workspace.

        Args:
            workspace_id: Workspace UUID
            container_id: Docker container ID
            name: Display name for the terminal

        Returns:
            Created TerminalSession object
        """
        session_id = str(uuid.uuid4())

        # Create exec instance with PTY
        try:
            client = docker.from_env()
            container = client.containers.get(container_id)

            # Create exec with TTY and interactive mode
            exec_instance = client.api.exec_create(
                container.id,
                cmd=["/bin/bash"],
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True,
                workdir="/workspace",
            )
            exec_id = exec_instance["Id"]

        except NotFound as e:
            logger.error(f"Container not found: {container_id}")
            raise ValueError("Container not found") from e
        except APIError as e:
            logger.error(f"Failed to create exec: {e}")
            raise RuntimeError(f"Failed to create terminal exec: {e}") from e

        # Save to database
        now = datetime.now(UTC).isoformat()
        row = {
            "session_id": session_id,
            "workspace_id": workspace_id,
            "exec_id": exec_id,
            "name": name,
            "is_active": True,
            "created_at": now,
        }

        result = self.supabase.table(self.table_name).insert(row).execute()

        if not result.data:
            raise RuntimeError("Failed to save terminal session to database")

        logger.info(f"Terminal session created: {session_id} for workspace {workspace_id}")
        return self._row_to_session(result.data[0])

    def get_session(self, session_id: str) -> TerminalSession | None:
        """
        Get a terminal session by ID.

        Args:
            session_id: Session UUID

        Returns:
            TerminalSession object or None if not found
        """
        logger.debug(f"[GET_SESSION] Looking up session: {session_id}")
        result = (
            self.supabase.table(self.table_name).select("*").eq("session_id", session_id).execute()
        )

        if not result.data:
            logger.debug(f"[GET_SESSION] Session not found: {session_id}")
            return None

        session = self._row_to_session(result.data[0])
        logger.debug(f"[GET_SESSION] Found session: {session_id}, active: {session.is_active}")
        return session

    def get_sessions_for_workspace(self, workspace_id: str) -> list[TerminalSession]:
        """
        Get all terminal sessions for a workspace.

        Args:
            workspace_id: Workspace UUID

        Returns:
            List of TerminalSession objects
        """
        result = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("is_active", True)
            .order("created_at", desc=False)
            .execute()
        )

        return [self._row_to_session(row) for row in result.data]

    async def start_stream(
        self, session_id: str, container_id: str, on_output: Callable[[bytes], None]
    ) -> Any | None:
        """
        Start the exec stream for a terminal session.

        Args:
            session_id: Session UUID
            container_id: Docker container ID
            on_output: Callback for output data

        Returns:
            Socket object for writing input, or None on failure
        """
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return None

        try:
            client = docker.from_env()

            # Check if exec is still valid and not already running
            try:
                exec_info = client.api.exec_inspect(session.exec_id)
                if exec_info.get("Running", False):
                    logger.warning(
                        f"Exec {session.exec_id[:12]} is already running for session {session_id}. "
                        "Creating new session."
                    )
                    # Create a new session with a fresh exec
                    new_session = self.create_session(
                        workspace_id=session.workspace_id,
                        container_id=container_id,
                        name=session.name,
                    )
                    # Update session_id to use the new one
                    session = new_session
                    logger.info(
                        f"Created new terminal session {new_session.session_id} to replace stale exec"
                    )
            except NotFound:
                logger.warning(
                    f"Exec {session.exec_id[:12]} not found for session {session_id}. Creating new session."
                )
                # Exec was deleted, create a new session
                new_session = self.create_session(
                    workspace_id=session.workspace_id,
                    container_id=container_id,
                    name=session.name,
                )
                session = new_session
                logger.info(
                    f"Created new terminal session {new_session.session_id} to replace missing exec"
                )
            except APIError as e:
                error_msg = str(e).lower()
                if "already running" in error_msg or "is running" in error_msg:
                    logger.warning(
                        f"Exec {session.exec_id[:12]} is already running. Creating new session."
                    )
                    # Create a new session with a fresh exec
                    new_session = self.create_session(
                        workspace_id=session.workspace_id,
                        container_id=container_id,
                        name=session.name,
                    )
                    session = new_session
                    logger.info(
                        f"Created new terminal session {new_session.session_id} to replace running exec"
                    )
                else:
                    raise

            # Start exec with socket connection
            socket = client.api.exec_start(
                session.exec_id,
                detach=False,
                tty=True,
                socket=True,
            )

            # Store the socket reference
            self._active_streams[session_id] = {
                "socket": socket,
                "exec_id": session.exec_id,
            }

            # Start reading output in background
            asyncio.create_task(self._read_output(session_id, socket, on_output))

            logger.info(f"Terminal stream started for session {session_id}")

            # Send initial newline to trigger prompt (helps with bash prompt timing)
            try:
                self._get_raw_socket(socket)
                # Small delay to let bash initialize
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.debug(f"Initial setup note: {e}")
            return socket

        except NotFound:
            logger.error(f"Container not found: {container_id}")
            return None
        except APIError as e:
            logger.error(f"Failed to start exec stream: {e}")
            return None

    def _get_raw_socket(self, socket: Any) -> Any:
        """Get the underlying socket, handling both Unix and Windows (NpipeSocket)."""
        # On Unix, socket has _sock attribute
        # On Windows, socket is NpipeSocket which can be used directly
        if hasattr(socket, "_sock"):
            return socket._sock
        return socket

    async def _read_output(
        self, session_id: str, socket: Any, on_output: Callable[[bytes], None]
    ) -> None:
        """
        Continuously read output from the exec socket.

        Args:
            session_id: Session UUID
            socket: Docker socket object
            on_output: Callback for output data
        """
        try:
            sock = self._get_raw_socket(socket)

            # Only set blocking mode if the socket supports it (not on Windows NpipeSocket)
            if hasattr(sock, "setblocking"):
                try:
                    sock.setblocking(False)
                except Exception:
                    pass  # Some socket types don't support non-blocking mode

            while session_id in self._active_streams:
                try:
                    # Use asyncio to read from socket in a thread pool
                    loop = asyncio.get_running_loop()
                    data = await loop.run_in_executor(
                        None, lambda s=sock: self._read_socket_data(s)
                    )

                    if data:
                        logger.debug(f"Terminal output for {session_id}: {len(data)} bytes")
                        # Check for commits in terminal output
                        self._check_for_commit(session_id, data)
                        # Check for dev server previews in terminal output
                        self._check_for_preview(session_id, data, on_output)
                        on_output(data)
                    else:
                        # No data, small sleep to prevent busy loop
                        await asyncio.sleep(0.02)

                except BlockingIOError:
                    await asyncio.sleep(0.02)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if session_id not in self._active_streams:
                        break
                    logger.debug(f"Read error: {e}")
                    await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            logger.debug(f"Output reader cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Output reader error for session {session_id}: {e}")
        finally:
            logger.info(f"Output reader stopped for session {session_id}")

    def _read_socket_data(self, sock: Any) -> bytes | None:
        """Read data from socket with timeout."""
        try:
            # Set timeout if supported
            if hasattr(sock, "settimeout"):
                sock.settimeout(0.1)

            # Read data - use read() for NpipeSocket on Windows, recv() for Unix sockets
            if hasattr(sock, "recv"):
                data = sock.recv(4096)
            elif hasattr(sock, "read"):
                data = sock.read(4096)
            else:
                return None

            return data if data else None
        except Exception:
            return None

    def write_input(self, session_id: str, data: bytes) -> bool:
        """
        Write input data to the terminal.

        Args:
            session_id: Session UUID
            data: Input bytes to write

        Returns:
            True if write was successful
        """
        stream_info = self._active_streams.get(session_id)
        if not stream_info:
            logger.warning(f"[WRITE_INPUT] No active stream for session {session_id}")
            # Try to get session and recreate stream if possible
            session = self.get_session(session_id)
            if session:
                logger.info(f"[WRITE_INPUT] Attempting to recreate stream for session {session_id}")
                # Note: Stream recreation should be handled by the WebSocket handler
            return False

        try:
            socket = stream_info["socket"]
            sock = self._get_raw_socket(socket)

            logger.debug(
                f"[WRITE_INPUT] Writing {len(data)} bytes to session {session_id}: {data[:50]!r}"
            )

            # Use sendall if available (Unix), otherwise use send or write (Windows NpipeSocket)
            if hasattr(sock, "sendall"):
                sock.sendall(data)
            elif hasattr(sock, "send"):
                sock.send(data)
            elif hasattr(sock, "write"):
                sock.write(data)
            else:
                logger.error(f"[WRITE_INPUT] Socket has no send method for session {session_id}")
                return False
            logger.debug(f"[WRITE_INPUT] Write successful for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"[WRITE_INPUT] Failed to write to terminal {session_id}: {e}")
            return False

    def resize_terminal(self, session_id: str, cols: int, rows: int) -> bool:
        """
        Resize the terminal PTY.

        Args:
            session_id: Session UUID
            cols: Number of columns
            rows: Number of rows

        Returns:
            True if resize was successful
        """
        stream_info = self._active_streams.get(session_id)
        if not stream_info:
            logger.warning(f"No active stream for session {session_id}")
            return False

        try:
            client = docker.from_env()
            client.api.exec_resize(
                stream_info["exec_id"],
                height=rows,
                width=cols,
            )
            logger.debug(f"Resized terminal {session_id} to {cols}x{rows}")
            return True
        except Exception as e:
            logger.error(f"Failed to resize terminal {session_id}: {e}")
            return False

    def close_session(self, session_id: str) -> bool:
        """
        Close a terminal session.

        Args:
            session_id: Session UUID

        Returns:
            True if closed successfully
        """
        logger.info(f"[CLOSE_SESSION] Closing session: {session_id}")
        # Remove from active streams
        if session_id in self._active_streams:
            logger.debug(f"[CLOSE_SESSION] Removing from active streams: {session_id}")
            try:
                socket = self._active_streams[session_id]["socket"]
                sock = self._get_raw_socket(socket)
                sock.close()
            except Exception as e:
                logger.debug(f"[CLOSE_SESSION] Socket close error (expected): {e}")
            del self._active_streams[session_id]
        else:
            logger.debug(f"[CLOSE_SESSION] Session not in active streams: {session_id}")

        # Clean up output buffer
        self._cleanup_session_buffer(session_id)

        # Update database
        self.supabase.table(self.table_name).update({"is_active": False}).eq(
            "session_id", session_id
        ).execute()

        logger.info(f"[CLOSE_SESSION] Terminal session closed: {session_id}")
        return True

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a terminal session from database.

        Args:
            session_id: Session UUID

        Returns:
            True if deleted successfully
        """
        self.close_session(session_id)

        self.supabase.table(self.table_name).delete().eq("session_id", session_id).execute()

        # Clean up output buffer
        self._cleanup_session_buffer(session_id)

        logger.info(f"Terminal session deleted: {session_id}")
        return True

    def delete_sessions_for_workspace(self, workspace_id: str) -> int:
        """
        Delete all terminal sessions for a workspace.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Number of sessions deleted
        """
        # Get all sessions for the workspace (both active and inactive)
        result = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        all_sessions = [self._row_to_session(row) for row in result.data]

        deleted_count = 0
        for session in all_sessions:
            try:
                self.close_session(session.session_id)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Error closing session {session.session_id}: {e}")

        # Delete all sessions from database
        self.supabase.table(self.table_name).delete().eq("workspace_id", workspace_id).execute()

        logger.info(f"Deleted {deleted_count} terminal sessions for workspace {workspace_id}")
        return deleted_count

    def _check_for_commit(self, session_id: str, output_data: bytes) -> None:
        """
        Check terminal output for git commit commands and update last_platform_commit.

        Args:
            session_id: Terminal session ID
            output_data: Raw terminal output bytes
        """
        try:
            # Get session to find workspace_id and container_id
            session = self.get_session(session_id)
            if not session:
                return

            # Decode output and add to buffer
            try:
                output_text = output_data.decode("utf-8", errors="replace")
            except Exception:
                return

            # Update buffer for this session
            if session_id not in self._output_buffers:
                self._output_buffers[session_id] = ""

            buffer = self._output_buffers[session_id] + output_text
            # Keep buffer size manageable
            if len(buffer) > self._max_buffer_size:
                buffer = buffer[-self._max_buffer_size :]
            self._output_buffers[session_id] = buffer

            # Check for commit success patterns
            # Pattern 1: Git prompt format "[branch_name commit_sha]" - e.g., "[main abc1234]"
            # Pattern 2: "commit abc1234" or "commit abc1234 (HEAD -> main)" from git log/show
            # Pattern 3: "Created commit abc1234" from git commit output
            # Pattern 4: "[main abc1234]" at end of line (git prompt)
            commit_patterns = [
                (
                    r"\[([^\]]+)\s+([a-f0-9]{7,40})\]\s*$",
                    True,
                ),  # [branch sha] at end of line (git prompt)
                (r"\[([^\]]+)\s+([a-f0-9]{7,40})\]", False),  # [branch sha] anywhere
                (
                    r"commit\s+([a-f0-9]{7,40})\s*(?:\(HEAD|$)",
                    True,
                ),  # commit sha followed by HEAD or end
                (r"Created\s+commit\s+([a-f0-9]{7,40})", True),  # Created commit sha
            ]

            for pattern, _require_end in commit_patterns:
                matches = re.findall(pattern, buffer, re.IGNORECASE | re.MULTILINE)
                if matches:
                    # Get the most recent match
                    if isinstance(matches[-1], tuple):
                        commit_sha = matches[-1][-1]  # Last element of tuple
                    else:
                        commit_sha = matches[-1]

                    # Validate SHA format (should be 7-40 hex characters)
                    if not re.match(r"^[a-f0-9]{7,40}$", commit_sha, re.IGNORECASE):
                        continue

                    # Check if we've already processed this commit
                    if session_id in self._last_processed_commits:
                        if self._last_processed_commits[session_id] == commit_sha:
                            continue  # Already processed this commit

                    # Mark as processed
                    self._last_processed_commits[session_id] = commit_sha

                    # Schedule update with a small delay to ensure commit is complete
                    asyncio.create_task(
                        self._update_last_platform_commit_delayed(session.workspace_id, session_id)
                    )
                    logger.info(
                        f"Detected commit {commit_sha[:7]} in terminal output for workspace {session.workspace_id}, will update last_platform_commit"
                    )
                    break

        except Exception as e:
            logger.debug(f"Error checking for commit in terminal output: {e}")

    def _extract_preview_ports(self, output_text: str) -> set[int]:
        """Extract candidate ports from output text."""
        ports: set[int] = set()
        for pattern in self._preview_patterns:
            for match in pattern.findall(output_text):
                try:
                    port = int(match)
                except (TypeError, ValueError):
                    continue
                if 1024 <= port <= 65535:
                    ports.add(port)
        return ports

    def _is_port_listening(self, container_id: str, port: int) -> bool:
        """Check if a port is listening inside the container."""
        commands = [
            "ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null",
            "netstat -lnt 2>/dev/null",
        ]
        for command in commands:
            exit_code, output = self.docker_client.exec_command(container_id, command)
            if exit_code != 0 or not output:
                continue
            if f":{port} " in output or f":{port}\n" in output or f":{port}\r\n" in output:
                return True
        return False

    def _check_for_preview(
        self, session_id: str, output_data: bytes, on_output: Callable[[bytes], None]
    ) -> None:
        """Check terminal output for dev server URLs and announce preview links."""
        try:
            output_text = output_data.decode("utf-8", errors="replace")
        except Exception:
            return

        ports = self._extract_preview_ports(output_text)
        if not ports:
            return

        for port in ports:
            announced = self._announced_ports.get(session_id, set())
            if port in announced:
                continue
            asyncio.create_task(self._handle_preview_detected(session_id, port, on_output))

    async def _handle_preview_detected(
        self, session_id: str, port: int, on_output: Callable[[bytes], None]
    ) -> None:
        """Verify server port and announce preview URL."""
        session = self.get_session(session_id)
        if not session:
            return

        from app.services.preview_proxy import get_preview_proxy
        from app.services.workspace_manager import get_workspace_manager

        workspace_manager = get_workspace_manager()
        workspace = workspace_manager.get_workspace(session.workspace_id)
        if not workspace or not workspace.container_id:
            return

        # Verify port is listening in container
        if not self._is_port_listening(workspace.container_id, port):
            return

        preview_proxy = get_preview_proxy()
        preview_url, url_type, _host_port = preview_proxy.build_preview_url(
            workspace_id=workspace.workspace_id,
            container_id=workspace.container_id,
            container_port=port,
            base_url=None,
        )

        if not preview_url:
            return

        preview_proxy.register_detected_server(
            workspace_id=workspace.workspace_id,
            container_id=workspace.container_id,
            port=port,
            server_type=None,
            preview_url=preview_url,
        )

        # Track announcement to avoid duplicates
        if session_id not in self._announced_ports:
            self._announced_ports[session_id] = set()
        self._announced_ports[session_id].add(port)

        message = (f"\r\n\x1b[32mPreview ready ({url_type}): {preview_url}\x1b[0m\r\n").encode()
        try:
            on_output(message)
        except Exception:
            pass

    async def _update_last_platform_commit_delayed(
        self, workspace_id: str, session_id: str
    ) -> None:
        """
        Wait a short delay then update last_platform_commit to ensure commit is complete.
        """
        # Wait 500ms to ensure the commit is fully written
        await asyncio.sleep(0.5)
        await self._update_last_platform_commit(workspace_id, session_id)

    async def _update_last_platform_commit(self, workspace_id: str, session_id: str) -> None:
        """
        Update last_platform_commit in database after detecting a commit in terminal.

        Args:
            workspace_id: Workspace UUID
            session_id: Terminal session ID
        """
        try:
            # Get workspace to find container_id
            from app.services.workspace_manager import get_workspace_manager

            workspace_manager = get_workspace_manager()
            workspace = workspace_manager.get_workspace(workspace_id)

            if not workspace or not workspace.container_id:
                logger.warning(
                    "Cannot update last_platform_commit: workspace or container not found"
                )
                return

            # Get current HEAD commit SHA
            rev_result = self.git_service.git_rev_parse(workspace.container_id, "HEAD")
            if not rev_result.get("success"):
                logger.warning(f"Failed to get HEAD commit SHA: {rev_result.get('error')}")
                return

            commit_sha = rev_result.get("sha")
            if not commit_sha:
                logger.warning("No commit SHA returned from git rev-parse")
                return

            # Get user_id from workspace
            user_id = workspace.user_id

            # Update last_platform_commit in database
            self.supabase.table("workspaces").update({"last_platform_commit": commit_sha}).eq(
                "workspace_id", workspace_id
            ).eq("user_id", user_id).execute()

            logger.info(
                f"Updated last_platform_commit to {commit_sha[:7]} for workspace {workspace_id} (detected from terminal)"
            )

        except Exception as e:
            logger.error(
                f"Failed to update last_platform_commit for workspace {workspace_id}: {e}",
                exc_info=True,
            )

    def _cleanup_session_buffer(self, session_id: str) -> None:
        """Clean up output buffer when session is closed."""
        if session_id in self._output_buffers:
            del self._output_buffers[session_id]
        if session_id in self._last_processed_commits:
            del self._last_processed_commits[session_id]
        if session_id in self._announced_ports:
            del self._announced_ports[session_id]


# Singleton instance
_terminal_service: TerminalService | None = None


def get_terminal_service() -> TerminalService:
    """Get or create the TerminalService singleton."""
    global _terminal_service
    if _terminal_service is None:
        _terminal_service = TerminalService()
    return _terminal_service
