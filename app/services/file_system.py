"""
File System Service
Provides file operations inside Docker containers using exec commands.
"""

import base64
import logging
from typing import List, Optional
from dataclasses import dataclass
from app.services.docker_client import get_docker_client, DockerClient

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Represents a file or directory in the container."""
    name: str
    path: str
    is_directory: bool
    size: int
    permissions: str
    
    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "is_directory": self.is_directory,
            "size": self.size,
            "permissions": self.permissions,
        }


class FileSystemService:
    """Service for file operations inside containers."""

    def __init__(self, docker_client: Optional[DockerClient] = None):
        self._docker_client = docker_client or get_docker_client()

    def list_files(self, container_id: str, path: str = "/workspace") -> List[FileInfo]:
        """
        List files and directories at the given path.

        Args:
            container_id: Docker container ID
            path: Path to list (default: /workspace)

        Returns:
            List of FileInfo objects
        """
        safe_path = self._sanitize_path(path)
        
        logger.info(f"Listing files in container {container_id[:12]} at path: {safe_path}")
        
        # Use ls with specific format for reliable parsing
        # -A: all except . and ..
        # -l: long format
        # --time-style=+%s: unix timestamp
        command = f"ls -Alh --time-style=+%s '{safe_path}' 2>/dev/null || echo 'ERROR_DIR_NOT_FOUND'"
        
        exit_code, output = self._docker_client.exec_command(container_id, command)
        
        # Check for docker client errors (exit_code -1)
        if exit_code == -1:
            logger.error(f"Docker exec failed for list_files: {output}")
            return []
        
        if "ERROR_DIR_NOT_FOUND" in output:
            logger.warning(f"Directory not found: {path}")
            return []
        
        files = []
        for line in output.strip().split('\n'):
            if not line or line.startswith('total'):
                continue
            
            file_info = self._parse_ls_line(line, safe_path)
            if file_info:
                files.append(file_info)
        
        logger.info(f"Found {len(files)} files in {safe_path}")
        
        # Sort: directories first, then by name
        files.sort(key=lambda f: (not f.is_directory, f.name.lower()))
        return files

    def read_file(self, container_id: str, path: str) -> Optional[str]:
        """
        Read file content from container.

        Args:
            container_id: Docker container ID
            path: File path to read

        Returns:
            File content as string, or None if error
        """
        safe_path = self._sanitize_path(path)
        
        logger.info(f"Reading file in container {container_id[:12]}: {safe_path}")
        
        # Check if file exists and is readable
        check_cmd = f"test -f '{safe_path}' && test -r '{safe_path}' && echo 'OK' || echo 'ERROR'"
        exit_code, output = self._docker_client.exec_command(container_id, check_cmd)
        
        # Check for docker client errors
        if exit_code == -1:
            logger.error(f"Docker exec failed for file check: {output}")
            return None
        
        if "ERROR" in output or "OK" not in output:
            logger.warning(f"File not found or not readable: {path}")
            return None
        
        # Read file using base64 to handle binary/special chars safely
        command = f"base64 '{safe_path}'"
        exit_code, output = self._docker_client.exec_command(container_id, command)
        
        if exit_code != 0:
            logger.error(f"Failed to read file {path}: exit_code={exit_code}, output={output[:200]}")
            return None
        
        try:
            # Decode base64 content
            content = base64.b64decode(output.strip()).decode('utf-8')
            logger.info(f"Successfully read file {safe_path} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.error(f"Failed to decode file content: {e}")
            return None

    def write_file(self, container_id: str, path: str, content: str) -> bool:
        """
        Write content to a file in the container.

        Args:
            container_id: Docker container ID
            path: File path to write
            content: Content to write

        Returns:
            True if successful
        """
        safe_path = self._sanitize_path(path)
        
        logger.info(f"Writing file in container {container_id[:12]}: {safe_path} ({len(content)} chars)")
        
        # Encode content as base64 to safely handle special characters
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
        
        # Create parent directory if needed, then write using base64 decode pipe to file
        # Split into multiple commands for reliability
        mkdir_cmd = f"mkdir -p \"$(dirname '{safe_path}')\""
        exit_code, output = self._docker_client.exec_command(container_id, mkdir_cmd)
        
        if exit_code != 0 and exit_code != -1:
            logger.warning(f"mkdir command returned {exit_code}: {output}")
        
        # Write file - use printf instead of echo to handle large content better
        # Also use a temp file approach for reliability
        write_cmd = f"printf '%s' '{encoded_content}' | base64 -d > '{safe_path}'"
        exit_code, output = self._docker_client.exec_command(container_id, write_cmd)
        
        if exit_code != 0:
            logger.error(f"Failed to write file {path}: exit_code={exit_code}, output={output[:200]}")
            return False
        
        # Verify the write
        verify_cmd = f"test -f '{safe_path}' && echo 'OK' || echo 'FAIL'"
        exit_code, output = self._docker_client.exec_command(container_id, verify_cmd)
        
        if "OK" not in output:
            logger.error(f"Write verification failed for {path}")
            return False
        
        logger.info(f"File written successfully: {safe_path}")
        return True

    def create_file(self, container_id: str, path: str) -> bool:
        """
        Create an empty file.

        Args:
            container_id: Docker container ID
            path: File path to create

        Returns:
            True if successful
        """
        safe_path = self._sanitize_path(path)
        
        logger.info(f"Creating file in container {container_id[:12]}: {safe_path}")
        
        # Extract parent directory from path (use posixpath for Unix-style paths)
        import posixpath
        parent_dir = posixpath.dirname(safe_path)
        
        # Create parent directory if it's not the workspace root
        if parent_dir and parent_dir != "/workspace":
            mkdir_cmd = f"mkdir -p '{parent_dir}'"
            exit_code, output = self._docker_client.exec_command(container_id, mkdir_cmd)
            if exit_code != 0 and exit_code != -1:
                logger.warning(f"mkdir returned {exit_code}: {output}")
        
        # Touch the file
        touch_cmd = f"touch '{safe_path}'"
        exit_code, output = self._docker_client.exec_command(container_id, touch_cmd)
        
        if exit_code != 0:
            logger.error(f"Failed to create file {path}: exit_code={exit_code}, output={output}")
            return False
        
        # Verify the file was created
        verify_cmd = f"test -f '{safe_path}' && echo 'OK' || echo 'FAIL'"
        exit_code, output = self._docker_client.exec_command(container_id, verify_cmd)
        
        if "OK" not in output:
            logger.error(f"File creation verification failed for {path}: {output}")
            return False
        
        logger.info(f"File created: {safe_path}")
        return True

    def create_directory(self, container_id: str, path: str) -> bool:
        """
        Create a directory.

        Args:
            container_id: Docker container ID
            path: Directory path to create

        Returns:
            True if successful
        """
        safe_path = self._sanitize_path(path)
        
        logger.info(f"Creating directory in container {container_id[:12]}: {safe_path}")
        
        command = f"mkdir -p '{safe_path}'"
        exit_code, output = self._docker_client.exec_command(container_id, command)
        
        if exit_code != 0:
            logger.error(f"Failed to create directory {path}: exit_code={exit_code}, output={output}")
            return False
        
        logger.info(f"Directory created: {safe_path}")
        return True

    def delete_file(self, container_id: str, path: str) -> bool:
        """
        Delete a file or directory.

        Args:
            container_id: Docker container ID
            path: Path to delete

        Returns:
            True if successful
        """
        safe_path = self._sanitize_path(path)
        
        # Prevent deleting workspace root
        if safe_path == "/workspace" or safe_path == "/workspace/":
            logger.error("Cannot delete workspace root")
            return False
        
        logger.info(f"Deleting in container {container_id[:12]}: {safe_path}")
        
        # Use rm -rf for both files and directories
        command = f"rm -rf '{safe_path}'"
        exit_code, output = self._docker_client.exec_command(container_id, command)
        
        if exit_code != 0:
            logger.error(f"Failed to delete {path}: exit_code={exit_code}, output={output}")
            return False
        
        logger.info(f"Deleted: {safe_path}")
        return True

    def rename_file(self, container_id: str, old_path: str, new_path: str) -> bool:
        """
        Rename/move a file or directory.

        Args:
            container_id: Docker container ID
            old_path: Current path
            new_path: New path

        Returns:
            True if successful
        """
        safe_old = self._sanitize_path(old_path)
        safe_new = self._sanitize_path(new_path)
        
        logger.info(f"Renaming in container {container_id[:12]}: {safe_old} -> {safe_new}")
        
        command = f"mv '{safe_old}' '{safe_new}'"
        exit_code, output = self._docker_client.exec_command(container_id, command)
        
        if exit_code != 0:
            logger.error(f"Failed to rename {old_path} to {new_path}: exit_code={exit_code}, output={output}")
            return False
        
        logger.info(f"Renamed: {safe_old} -> {safe_new}")
        return True

    def file_exists(self, container_id: str, path: str) -> bool:
        """
        Check if a file or directory exists.

        Args:
            container_id: Docker container ID
            path: Path to check

        Returns:
            True if exists
        """
        safe_path = self._sanitize_path(path)
        
        command = f"test -e '{safe_path}' && echo 'EXISTS' || echo 'NOT_FOUND'"
        exit_code, output = self._docker_client.exec_command(container_id, command)
        
        return "EXISTS" in output

    def _sanitize_path(self, path: str) -> str:
        """
        Sanitize file path to prevent command injection.
        Ensures path is under /workspace.
        Uses posixpath for Unix-style paths (Docker containers).
        """
        import posixpath
        
        # Remove any null bytes
        path = path.replace('\x00', '')
        
        # Convert any Windows backslashes to forward slashes
        path = path.replace('\\', '/')
        
        # Normalize path using posixpath (keeps forward slashes)
        path = posixpath.normpath(path)
        
        # Ensure path starts with /workspace
        if not path.startswith('/workspace'):
            path = f"/workspace/{path.lstrip('/')}"
        
        # Normalize again and verify
        path = posixpath.normpath(path)
        if not path.startswith('/workspace'):
            path = '/workspace'
        
        return path

    def _parse_ls_line(self, line: str, base_path: str) -> Optional[FileInfo]:
        """
        Parse a line from ls -l output.
        
        Example: -rw-r--r-- 1 developer developer 36 1704067200 hello.js
        """
        parts = line.split()
        if len(parts) < 7:
            logger.debug(f"Skipping malformed ls line (< 7 parts): {line}")
            return None
        
        permissions = parts[0]
        is_directory = permissions.startswith('d')
        
        # Size is typically the 5th column (index 4)
        try:
            size_str = parts[4]
            # Handle human-readable sizes (e.g., 4.0K, 1.2M)
            size = self._parse_size(size_str)
        except (ValueError, IndexError):
            size = 0
        
        # Name is the last part (may contain spaces, so join from index 6)
        name = ' '.join(parts[6:])
        
        # Skip . and ..
        if name in ['.', '..']:
            return None
        
        # Build full path
        if base_path.endswith('/'):
            full_path = f"{base_path}{name}"
        else:
            full_path = f"{base_path}/{name}"
        
        return FileInfo(
            name=name,
            path=full_path,
            is_directory=is_directory,
            size=size,
            permissions=permissions,
        )

    def _parse_size(self, size_str: str) -> int:
        """Parse size string (handles K, M, G suffixes)."""
        size_str = size_str.strip()
        if not size_str:
            return 0
        
        multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
        
        if size_str[-1].upper() in multipliers:
            try:
                number = float(size_str[:-1])
                return int(number * multipliers[size_str[-1].upper()])
            except ValueError:
                return 0
        
        try:
            return int(size_str)
        except ValueError:
            return 0


# Singleton instance
_file_system_service: Optional[FileSystemService] = None


def get_file_system_service() -> FileSystemService:
    """Get or create the FileSystemService singleton."""
    global _file_system_service
    if _file_system_service is None:
        _file_system_service = FileSystemService()
    return _file_system_service
