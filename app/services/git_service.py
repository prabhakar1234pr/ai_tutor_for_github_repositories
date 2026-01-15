"""
Git Service
Runs git commands inside Docker workspaces and returns structured results.
"""

import logging
import re
import shlex
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.services.docker_client import DockerClient, get_docker_client

logger = logging.getLogger(__name__)


@dataclass
class GitCommandResult:
    exit_code: int
    output: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class GitService:
    """Service wrapper for git operations inside workspace containers."""

    def __init__(self, docker_client: Optional[DockerClient] = None):
        self._docker = docker_client or get_docker_client()

    def clone_repository(self, container_id: str, repo_url: str, token: Optional[str] = None) -> Dict[str, str]:
        """
        Clone repository into /workspace.

        Returns:
            {"status": "cloned" | "already_cloned", "message": str}
        """
        repo_url = repo_url.strip()
        auth_url = self._inject_token(repo_url, token) if token else repo_url
        safe_auth_url = self._redact_token(auth_url)

        logger.info(f"Cloning repository into container {container_id[:12]}: {safe_auth_url}")

        check_cmd = "if [ -d /workspace/.git ]; then echo 'ALREADY_CLONED'; else echo 'NOT_CLONED'; fi"
        exit_code, output = self._exec(container_id, check_cmd)
        if exit_code != 0:
            return {"status": "error", "message": output}
        if "ALREADY_CLONED" in output:
            return {"status": "already_cloned", "message": "Repository already cloned"}

        empty_check = "if [ -z \"$(ls -A /workspace 2>/dev/null)\" ]; then echo 'EMPTY'; else echo 'NOT_EMPTY'; fi"
        exit_code, output = self._exec(container_id, empty_check)
        if exit_code != 0:
            return {"status": "error", "message": output}
        if "NOT_EMPTY" in output:
            return {"status": "error", "message": "Workspace is not empty; cannot clone into /workspace"}

        cmd = f"git clone {shlex.quote(auth_url)} /workspace"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"status": "error", "message": output}

        return {"status": "cloned", "message": "Repository cloned successfully"}

    def git_status(self, container_id: str) -> Dict[str, object]:
        """
        Get git status with parsed file lists and branch info.
        """
        cmd = "git status --porcelain=v1 -b"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        lines = [line for line in output.splitlines() if line.strip()]
        branch_info = {}
        modified: List[str] = []
        staged: List[str] = []
        untracked: List[str] = []
        conflicts: List[str] = []

        if lines and lines[0].startswith("##"):
            branch_info = self._parse_branch_info(lines[0])
            lines = lines[1:]

        for line in lines:
            if line.startswith("??"):
                untracked.append(line[3:].strip())
                continue

            if len(line) < 3:
                continue

            index_status = line[0]
            worktree_status = line[1]
            path = line[3:].strip()

            if index_status in {"U", "A", "D", "M", "R", "C"} and worktree_status in {"U", "A", "D", "M"}:
                conflicts.append(path)
                continue

            if index_status != " ":
                staged.append(path)
            if worktree_status != " ":
                modified.append(path)

        return {
            "success": True,
            "branch": branch_info.get("branch"),
            "ahead": branch_info.get("ahead", 0),
            "behind": branch_info.get("behind", 0),
            "modified": sorted(set(modified)),
            "staged": sorted(set(staged)),
            "untracked": sorted(set(untracked)),
            "conflicts": sorted(set(conflicts)),
            "raw": output,
        }

    def git_diff(self, container_id: str, base_commit: Optional[str] = None, head_commit: Optional[str] = None) -> Dict[str, str]:
        """
        Get git diff between base_commit and head_commit (default HEAD).
        """
        base = base_commit.strip() if base_commit else ""
        head = head_commit.strip() if head_commit else "HEAD"

        if base:
            cmd = f"git diff {shlex.quote(base)}..{shlex.quote(head)}"
        else:
            cmd = "git diff"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "diff": output}

    def git_commit(
        self,
        container_id: str,
        message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Stage all changes and create a commit.
        """
        if not message.strip():
            return {"success": False, "error": "Commit message is required"}

        add_cmd = "git add -A"
        exit_code, output = self._exec(container_id, add_cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        env_prefix = self._author_env(author_name, author_email)
        commit_cmd = f"{env_prefix}git commit -m {shlex.quote(message)}"
        exit_code, output = self._exec(container_id, commit_cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        sha = self.git_rev_parse(container_id, "HEAD")
        return {"success": True, "commit_sha": sha.get("sha"), "output": output}

    def git_push(self, container_id: str, branch: str, token: Optional[str] = None, force: bool = False) -> Dict[str, str]:
        """
        Push to remote using token if provided.
        """
        branch = branch.strip() or "main"
        remote_url = self._get_remote_url(container_id)
        if not remote_url:
            return {"success": False, "error": "Remote 'origin' not found"}

        auth_url = self._inject_token(remote_url, token) if token else remote_url
        safe_auth_url = self._redact_token(auth_url)

        flags = "--force" if force else ""
        cmd = f"git push {shlex.quote(auth_url)} {shlex.quote(branch)} {flags}".strip()
        logger.info(f"Pushing to remote: {safe_auth_url} ({branch})")

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_pull(self, container_id: str, branch: str, token: Optional[str] = None) -> Dict[str, str]:
        """
        Pull from remote using token if provided.
        """
        branch = branch.strip() or "main"
        remote_url = self._get_remote_url(container_id)
        if not remote_url:
            return {"success": False, "error": "Remote 'origin' not found"}

        auth_url = self._inject_token(remote_url, token) if token else remote_url
        safe_auth_url = self._redact_token(auth_url)

        cmd = f"git pull {shlex.quote(auth_url)} {shlex.quote(branch)}"
        logger.info(f"Pulling from remote: {safe_auth_url} ({branch})")

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_stash(self, container_id: str, message: Optional[str] = None) -> Dict[str, str]:
        """
        Stash uncommitted changes (including untracked).
        """
        msg = message.strip() if message else "WIP: auto-stash"
        cmd = f"git stash push -u -m {shlex.quote(msg)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_discard(self, container_id: str) -> Dict[str, str]:
        """
        Discard all uncommitted changes and untracked files.
        """
        cmd = "git reset --hard && git clean -fd"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_rev_parse(self, container_id: str, ref: str) -> Dict[str, str]:
        """
        Get commit SHA for a ref (e.g., HEAD).
        """
        cmd = f"git rev-parse {shlex.quote(ref)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "sha": output.strip()}

    def git_current_branch(self, container_id: str) -> Dict[str, str]:
        """
        Get current branch name.
        """
        cmd = "git rev-parse --abbrev-ref HEAD"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "branch": output.strip()}

    def git_log(self, container_id: str, range_spec: Optional[str] = None, max_count: int = 50) -> Dict[str, object]:
        """
        Get commit list for a range.
        """
        range_part = shlex.quote(range_spec) if range_spec else ""
        format_spec = "%H%x7C%an%x7C%ae%x7C%ad%x7C%s"
        cmd = (
            "git log "
            f"{range_part} --max-count={int(max_count)} "
            f"--pretty=format:{format_spec} --date=iso"
        ).strip()
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        commits = []
        for line in output.splitlines():
            parts = line.split("|", 4)
            if len(parts) != 5:
                continue
            commits.append(
                {
                    "sha": parts[0],
                    "author_name": parts[1],
                    "author_email": parts[2],
                    "date": parts[3],
                    "message": parts[4],
                }
            )

        return {"success": True, "commits": commits}

    def git_check_uncommitted(self, container_id: str) -> Dict[str, object]:
        """
        Check for uncommitted changes.
        """
        cmd = "git status --porcelain=v1"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        files = [line[3:].strip() for line in output.splitlines() if line.strip()]
        return {"success": True, "has_changes": len(files) > 0, "files": files}

    def git_reset_hard(self, container_id: str, commit: str) -> Dict[str, str]:
        """
        Hard reset to a commit.
        """
        cmd = f"git reset --hard {shlex.quote(commit)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_ls_remote(self, container_id: str, remote: str, branch: str) -> Dict[str, str]:
        """
        Get remote SHA for a branch.
        """
        cmd = f"git ls-remote {shlex.quote(remote)} {shlex.quote(branch)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        sha = output.split()[0] if output.strip() else ""
        return {"success": True, "sha": sha}

    def git_current_branch(self, container_id: str) -> Dict[str, str]:
        """
        Get current branch name.
        """
        cmd = "git rev-parse --abbrev-ref HEAD"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "branch": output.strip()}

    def configure_git_user(self, container_id: str, name: str, email: str) -> Dict[str, str]:
        """
        Configure git user.name and user.email.
        """
        if not name.strip() or not email.strip():
            return {"success": False, "error": "Name and email are required"}

        cmd = f"git config user.name {shlex.quote(name)} && git config user.email {shlex.quote(email)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def _exec(self, container_id: str, command: str) -> Tuple[int, str]:
        return self._docker.exec_command(container_id, command, workdir="/workspace")

    def _get_remote_url(self, container_id: str) -> Optional[str]:
        exit_code, output = self._exec(container_id, "git remote get-url origin")
        if exit_code != 0:
            return None
        return output.strip()

    @staticmethod
    def _author_env(author_name: Optional[str], author_email: Optional[str]) -> str:
        if not author_name or not author_email:
            return ""
        name = shlex.quote(author_name)
        email = shlex.quote(author_email)
        return (
            f"GIT_AUTHOR_NAME={name} GIT_AUTHOR_EMAIL={email} "
            f"GIT_COMMITTER_NAME={name} GIT_COMMITTER_EMAIL={email} "
        )

    @staticmethod
    def _inject_token(repo_url: str, token: str) -> str:
        """
        Inject token into HTTPS URL for auth.
        """
        token = token.strip()
        if repo_url.startswith("https://"):
            return repo_url.replace("https://", f"https://x-access-token:{token}@")
        if repo_url.startswith("http://"):
            return repo_url.replace("http://", f"http://x-access-token:{token}@")
        return repo_url

    @staticmethod
    def _redact_token(repo_url: str) -> str:
        return re.sub(r"(https?://)([^@]+)@", r"\1***@", repo_url)

    @staticmethod
    def _parse_branch_info(line: str) -> Dict[str, object]:
        # Example: "## main...origin/main [ahead 1, behind 2]"
        info = {"branch": None, "ahead": 0, "behind": 0}
        match = re.match(r"##\s+([^\s.]+)", line)
        if match:
            info["branch"] = match.group(1)
        ahead_match = re.search(r"ahead\s+(\d+)", line)
        behind_match = re.search(r"behind\s+(\d+)", line)
        if ahead_match:
            info["ahead"] = int(ahead_match.group(1))
        if behind_match:
            info["behind"] = int(behind_match.group(1))
        return info
