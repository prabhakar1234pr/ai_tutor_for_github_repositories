"""
Terminal Service
Manages PTY sessions for interactive terminal access in Docker containers.
"""

import asyncio
import uuid
import logging
from typing import Optional, Dict, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timezone
import docker
from docker.errors import NotFound, APIError

from app.core.supabase_client import get_supabase_client
from app.services.docker_client import get_docker_client

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
        self.table_name = "terminal_sessions"
        # Active exec streams: session_id -> (socket, exec_id)
        self._active_streams: Dict[str, Any] = {}

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
        self,
        workspace_id: str,
        container_id: str,
        name: str = "Terminal"
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

        except NotFound:
            logger.error(f"Container not found: {container_id}")
            raise ValueError("Container not found")
        except APIError as e:
            logger.error(f"Failed to create exec: {e}")
            raise RuntimeError(f"Failed to create terminal exec: {e}")

        # Save to database
        now = datetime.now(timezone.utc).isoformat()
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

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """
        Get a terminal session by ID.

        Args:
            session_id: Session UUID

        Returns:
            TerminalSession object or None if not found
        """
        logger.debug(f"[GET_SESSION] Looking up session: {session_id}")
        result = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("session_id", session_id)
            .execute()
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
        self,
        session_id: str,
        container_id: str,
        on_output: Callable[[bytes], None]
    ) -> Optional[Any]:
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
            asyncio.create_task(
                self._read_output(session_id, socket, on_output)
            )

            logger.info(f"Terminal stream started for session {session_id}")
            
            # Send initial newline to trigger prompt (helps with bash prompt timing)
            try:
                sock = self._get_raw_socket(socket)
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
        if hasattr(socket, '_sock'):
            return socket._sock
        return socket

    async def _read_output(
        self,
        session_id: str,
        socket: Any,
        on_output: Callable[[bytes], None]
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
            if hasattr(sock, 'setblocking'):
                try:
                    sock.setblocking(False)
                except Exception:
                    pass  # Some socket types don't support non-blocking mode

            while session_id in self._active_streams:
                try:
                    # Use asyncio to read from socket in a thread pool
                    loop = asyncio.get_running_loop()
                    data = await loop.run_in_executor(
                        None,
                        lambda s=sock: self._read_socket_data(s)
                    )
                    
                    if data:
                        logger.debug(f"Terminal output for {session_id}: {len(data)} bytes")
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

    def _read_socket_data(self, sock: Any) -> Optional[bytes]:
        """Read data from socket with timeout."""
        try:
            # Set timeout if supported
            if hasattr(sock, 'settimeout'):
                sock.settimeout(0.1)
            
            # Read data - use read() for NpipeSocket on Windows, recv() for Unix sockets
            if hasattr(sock, 'recv'):
                data = sock.recv(4096)
            elif hasattr(sock, 'read'):
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
            return False

        try:
            socket = stream_info["socket"]
            sock = self._get_raw_socket(socket)
            
            logger.debug(f"[WRITE_INPUT] Writing {len(data)} bytes to session {session_id}: {data[:50]!r}")
            
            # Use sendall if available (Unix), otherwise use send or write (Windows NpipeSocket)
            if hasattr(sock, 'sendall'):
                sock.sendall(data)
            elif hasattr(sock, 'send'):
                sock.send(data)
            elif hasattr(sock, 'write'):
                sock.write(data)
            else:
                logger.error(f"[WRITE_INPUT] Socket has no send method for session {session_id}")
                return False
            logger.debug(f"[WRITE_INPUT] Write successful for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"[WRITE_INPUT] Failed to write to terminal {session_id}: {e}")
            return False

    def resize_terminal(
        self,
        session_id: str,
        cols: int,
        rows: int
    ) -> bool:
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

        # Update database
        self.supabase.table(self.table_name).update(
            {"is_active": False}
        ).eq("session_id", session_id).execute()

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
        
        self.supabase.table(self.table_name).delete().eq(
            "session_id", session_id
        ).execute()

        logger.info(f"Terminal session deleted: {session_id}")
        return True


# Singleton instance
_terminal_service: Optional[TerminalService] = None


def get_terminal_service() -> TerminalService:
    """Get or create the TerminalService singleton."""
    global _terminal_service
    if _terminal_service is None:
        _terminal_service = TerminalService()
    return _terminal_service

