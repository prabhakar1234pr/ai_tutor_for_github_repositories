"""
Git Service
Runs git commands inside Docker workspaces and returns structured results.
"""

import logging
import re
import shlex
from dataclasses import dataclass

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

    def __init__(self, docker_client: DockerClient | None = None):
        self._docker = docker_client or get_docker_client()

    def clone_repository(
        self, container_id: str, repo_url: str, token: str | None = None
    ) -> dict[str, str]:
        """
        Clone repository into /workspace.
        If workspace is not empty but not a git repository, cleans it before cloning.

        Returns:
            {"status": "cloned" | "already_cloned", "message": str}
        """
        repo_url = repo_url.strip()
        auth_url = self._inject_token(repo_url, token) if token else repo_url
        safe_auth_url = self._redact_token(auth_url)

        logger.info(f"Cloning repository into container {container_id[:12]}: {safe_auth_url}")

        check_cmd = (
            "if [ -d /workspace/.git ]; then echo 'ALREADY_CLONED'; else echo 'NOT_CLONED'; fi"
        )
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
            # Workspace is not empty but also not a git repository (we checked above).
            # We must not destroy user files. Move existing contents to a backup folder,
            # then proceed to clone into /workspace (repo files will coexist with backup).
            logger.info("Workspace is not empty; backing up existing contents before clone...")
            backup_cmd = (
                "backup_dir=/workspace/.gitguide_backup_$(date +%s); "
                'mkdir -p "$backup_dir" && '
                'backup_name=$(basename "$backup_dir"); '
                "find /workspace -mindepth 1 -maxdepth 1 "
                '! -name "$backup_name" '
                '-exec mv -n {} "$backup_dir"/ \\; '
                '&& echo "Backed up existing workspace contents to $backup_dir"'
            )
            exit_code, backup_output = self._exec(container_id, backup_cmd)
            if exit_code != 0:
                return {
                    "status": "error",
                    "message": f"Failed to backup workspace before cloning: {backup_output}",
                }

        # Clone into a temporary directory, then move contents to /workspace
        # Git clone doesn't work well with . as target, so we clone to a temp dir first
        temp_dir = "/tmp/git-clone-temp"
        # Clone to temp directory
        clone_cmd = f"rm -rf {temp_dir} && git clone {shlex.quote(auth_url)} {temp_dir}"
        exit_code, output = self._exec(container_id, clone_cmd)
        if exit_code != 0:
            return {"status": "error", "message": output}

        # Move all contents including hidden files using find
        # This handles .git and other hidden files correctly
        move_cmd = f"find {temp_dir} -mindepth 1 -maxdepth 1 -exec mv {{}} /workspace/ \\; && rm -rf {temp_dir}"
        exit_code, output = self._exec(container_id, move_cmd)
        if exit_code != 0:
            # Clean up temp dir on failure
            self._exec(container_id, f"rm -rf {temp_dir}")
            return {"status": "error", "message": f"Failed to move cloned files: {output}"}

        return {"status": "cloned", "message": "Repository cloned successfully"}

    def git_status(self, container_id: str) -> dict[str, object]:
        """
        Get git status with parsed file lists and branch info.
        """
        cmd = "git status --porcelain=v1 -b"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        lines = [line for line in output.splitlines() if line.strip()]
        branch_info = {}
        modified: list[str] = []
        staged: list[str] = []
        untracked: list[str] = []
        deleted: list[str] = []
        conflicts: list[str] = []

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

            # Handle conflicts first
            if index_status in {"U", "A", "D", "M", "R", "C"} and worktree_status in {
                "U",
                "A",
                "D",
                "M",
            }:
                conflicts.append(path)
                continue

            # Track deleted files separately
            # " D" = deleted in working tree (unstaged deletion)
            # "D " = deleted in index (staged deletion)
            # "DD" = deleted in both (conflict - already handled above)
            is_deleted = False
            if worktree_status == "D" and index_status == " ":
                # Deleted in working tree, not staged
                deleted.append(path)
                modified.append(path)  # Also add to modified for backward compatibility
                is_deleted = True
            elif index_status == "D" and worktree_status == " ":
                # Deleted in index (staged)
                deleted.append(path)
                staged.append(path)
                is_deleted = True

            # Track staged changes (non-deleted files)
            if not is_deleted and index_status != " ":
                staged.append(path)

            # Track modified changes (non-deleted files)
            if not is_deleted and worktree_status != " ":
                modified.append(path)

        return {
            "success": True,
            "branch": branch_info.get("branch"),
            "ahead": branch_info.get("ahead", 0),
            "behind": branch_info.get("behind", 0),
            "modified": sorted(set(modified)),
            "staged": sorted(set(staged)),
            "untracked": sorted(set(untracked)),
            "deleted": sorted(set(deleted)),
            "conflicts": sorted(set(conflicts)),
            "raw": output,
        }

    def git_diff(
        self,
        container_id: str,
        base_commit: str | None = None,
        head_commit: str | None = None,
    ) -> dict[str, str]:
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

    def git_add(self, container_id: str, files: list[str] | None = None) -> dict[str, str]:
        """
        Stage files. If files is None or empty, stages all changes.

        Args:
            container_id: Container ID
            files: List of file paths to stage (relative to workspace root)
                  If None or empty, stages all changes (git add -A)

        Returns:
            Dict with success status and output
        """
        if files and len(files) > 0:
            # Stage specific files
            safe_files = [shlex.quote(f) for f in files]
            cmd = f"git add {' '.join(safe_files)}"
        else:
            # Stage all changes
            cmd = "git add -A"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_reset(
        self, container_id: str, files: list[str] | None = None, mode: str = "mixed"
    ) -> dict[str, str]:
        """
        Unstage files or reset changes.

        Args:
            container_id: Container ID
            files: List of file paths to unstage (relative to workspace root)
                  If None or empty, unstages all staged files
            mode: Reset mode - "mixed" (default, unstage), "hard" (discard changes)

        Returns:
            Dict with success status and output
        """
        if files and len(files) > 0:
            # Unstage specific files
            safe_files = [shlex.quote(f) for f in files]
            cmd = f"git reset --{mode} {' '.join(safe_files)}"
        else:
            # Unstage all files
            cmd = f"git reset --{mode}"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_get_file_diff(
        self, container_id: str, file_path: str, staged: bool = False
    ) -> dict[str, str]:
        """
        Get diff for a specific file.
        Handles both tracked and untracked files.

        Args:
            container_id: Container ID
            file_path: Path to file (relative to workspace root)
            staged: If True, shows diff of staged changes. If False, shows diff of unstaged changes.

        Returns:
            Dict with success status and diff output
        """
        safe_path = shlex.quote(file_path)

        # Check if file is untracked (new file)
        check_cmd = f"git ls-files --error-unmatch {safe_path}"
        check_exit, _ = self._exec(container_id, check_cmd)
        is_untracked = check_exit != 0

        if is_untracked:
            # For untracked files, show the entire file as new content
            # Read the file content and format as a diff
            read_cmd = f"cat {safe_path}"
            read_exit, file_content = self._exec(container_id, read_cmd)
            if read_exit != 0:
                return {"success": False, "error": f"Failed to read file: {file_content}"}

            # Format as a new file diff
            lines = file_content.splitlines()
            diff_lines = [
                f"diff --git a/{file_path} b/{file_path}",
                "new file mode 100644",
                "index 0000000..0000000",
                "--- /dev/null",
                f"+++ b/{file_path}",
            ]
            if lines:
                diff_lines.append("@@ -0,0 +1," + str(len(lines)) + " @@")
                for line in lines:
                    diff_lines.append(f"+{line}")
            else:
                diff_lines.append("@@ -0,0 +1,0 @@")
                diff_lines.append("+")

            return {"success": True, "diff": "\n".join(diff_lines), "is_new_file": True}

        # For tracked files, use normal git diff
        if staged:
            # Show diff of staged changes
            cmd = f"git diff --cached {safe_path}"
        else:
            # Show diff of unstaged changes
            cmd = f"git diff {safe_path}"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            # Empty diff is valid (no changes)
            if not output.strip():
                return {"success": True, "diff": "", "is_new_file": False}
            return {"success": False, "error": output}

        # Empty diff is valid
        return {"success": True, "diff": output, "is_new_file": False}

    def git_commit(
        self,
        container_id: str,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, str]:
        """
        Create a commit with staged files only.
        Note: Files must be staged separately using git_add() before committing.
        """
        if not message.strip():
            return {"success": False, "error": "Commit message is required"}

        env_prefix = self._author_env(author_name, author_email)
        commit_cmd = f"{env_prefix}git commit -m {shlex.quote(message)}"
        exit_code, output = self._exec(container_id, commit_cmd)
        if exit_code != 0:
            if "nothing to commit" in output.lower():
                return {
                    "success": False,
                    "error": "Nothing to commit. Stage files first using git add.",
                }
            logger.error(f"Git commit failed: {output}")
            return {"success": False, "error": output}

        sha = self.git_rev_parse(container_id, "HEAD")
        return {"success": True, "commit_sha": sha.get("sha"), "output": output}

    def git_push(
        self,
        container_id: str,
        branch: str,
        token: str | None = None,
        force: bool = False,
        set_upstream: bool = False,
    ) -> dict[str, str]:
        """
        Push to remote using token if provided.
        Updates remote URL with token if needed, then pushes to origin.

        Args:
            container_id: Container ID
            branch: Branch name to push
            token: GitHub token for authentication
            force: Force push flag
            set_upstream: Set upstream tracking (use -u flag). Useful for new branches.
        """
        branch = branch.strip() or "main"
        remote_url = self._get_remote_url(container_id)
        if not remote_url:
            return {"success": False, "error": "Remote 'origin' not found"}

        # Update remote URL with token if provided
        if token:
            auth_url = self._inject_token(remote_url, token)
            logger.debug(
                f"Updating remote URL from: {self._redact_token(remote_url)} to: {self._redact_token(auth_url)}"
            )
            set_result = self.git_set_remote_url(container_id, auth_url)
            if not set_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to update remote URL: {set_result.get('error')}",
                }
            # Verify the URL was set correctly
            verify_url = self._get_remote_url(container_id)
            if verify_url:
                logger.debug(f"Verified remote URL: {self._redact_token(verify_url)}")

        # Check if branch exists on remote to determine if we need upstream tracking
        # For new branches, we need -u flag to set upstream tracking
        upstream_flag = "-u" if set_upstream else ""
        force_flag = "--force" if force else ""
        flags = " ".join([f for f in [upstream_flag, force_flag] if f]).strip()

        cmd = f"git push origin {shlex.quote(branch)} {flags}".strip()
        final_url = self._get_remote_url(container_id) or remote_url
        safe_url = self._redact_token(final_url)
        logger.info(
            f"Pushing to remote: {safe_url} ({branch}) {'with upstream' if set_upstream else ''}"
        )

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            logger.error(f"Git push failed: {output}")
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_pull(self, container_id: str, branch: str, token: str | None = None) -> dict[str, str]:
        """
        Pull from remote using token if provided.
        Updates remote URL with token if needed, then pulls from origin.
        """
        branch = branch.strip() or "main"
        remote_url = self._get_remote_url(container_id)
        if not remote_url:
            return {"success": False, "error": "Remote 'origin' not found"}

        # Update remote URL with token if provided
        if token:
            auth_url = self._inject_token(remote_url, token)
            set_result = self.git_set_remote_url(container_id, auth_url)
            if not set_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to update remote URL: {set_result.get('error')}",
                }

        cmd = f"git pull origin {shlex.quote(branch)}"
        safe_url = self._redact_token(remote_url)
        logger.info(f"Pulling from remote: {safe_url} ({branch})")

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            logger.error(f"Git pull failed: {output}")
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_get_remote_url(self, container_id: str) -> dict[str, str]:
        """
        Get remote origin URL.
        """
        exit_code, output = self._exec(container_id, "git remote get-url origin")
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "url": output.strip()}

    def git_set_remote_url(self, container_id: str, remote_url: str) -> dict[str, str]:
        """
        Set remote origin URL.
        Removes trailing slashes as git doesn't like them.
        """
        # Remove trailing slash - git remote URLs shouldn't have them
        clean_url = remote_url.strip().rstrip("/")
        cmd = f"git remote set-url origin {shlex.quote(clean_url)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_stash(self, container_id: str, message: str | None = None) -> dict[str, str]:
        """
        Stash uncommitted changes (including untracked).
        """
        msg = message.strip() if message else "WIP: auto-stash"
        cmd = f"git stash push -u -m {shlex.quote(msg)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_discard(self, container_id: str) -> dict[str, str]:
        """
        Discard all uncommitted changes and untracked files.
        """
        cmd = "git reset --hard && git clean -fd"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_rev_parse(self, container_id: str, ref: str) -> dict[str, str]:
        """
        Get commit SHA for a ref (e.g., HEAD).
        """
        cmd = f"git rev-parse {shlex.quote(ref)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "sha": output.strip()}

    def git_current_branch(self, container_id: str) -> dict[str, str]:
        """
        Get current branch name.
        """
        cmd = "git rev-parse --abbrev-ref HEAD"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "branch": output.strip()}

    def git_log(
        self,
        container_id: str,
        range_spec: str | None = None,
        max_count: int = 50,
        show_all: bool = False,
    ) -> dict[str, object]:
        """
        Get commit list for a range.

        Args:
            container_id: Container ID
            range_spec: Git range spec (e.g., "HEAD~5..HEAD" or "main..feature")
            max_count: Maximum number of commits
            show_all: If True, show all branches. If False and no range_spec, show only HEAD history.
        """
        if range_spec:
            range_part = shlex.quote(range_spec)
        elif show_all:
            range_part = "--all"
        else:
            range_part = "HEAD"  # Default to current branch history only

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

    def git_log_graph(
        self, container_id: str, max_count: int = 50, show_all: bool = False
    ) -> dict[str, object]:
        """
        Get commit graph with parent relationships for visualization.

        Args:
            container_id: Container ID
            max_count: Maximum number of commits to return
            show_all: If True, show all branches (including remote). If False, only show commits reachable from HEAD.
        """
        format_spec = "%H%x7C%P%x7C%an%x7C%ae%x7C%ad%x7C%s%x7C%D"
        # Use --all only if show_all is True, otherwise just show HEAD (current branch and its history)
        all_flag = "--all" if show_all else "HEAD"
        cmd = (
            f"git log {all_flag} --max-count={int(max_count)} "
            f"--pretty=format:{format_spec} --date=iso --decorate"
        ).strip()
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        commits = []
        branches = {}
        for line in output.splitlines():
            parts = line.split("|", 6)
            if len(parts) < 6:
                continue

            sha = parts[0]
            parents = [p.strip() for p in parts[1].split() if p.strip()] if parts[1] else []
            refs = parts[6] if len(parts) > 6 else ""

            # Parse branch/tag names from refs
            branch_names = []
            if refs:
                # Extract branch names from refs like "HEAD -> main, origin/main, tag: v1.0"
                import re

                branch_matches = re.findall(r"(?:HEAD -> |origin/)?([^,]+)", refs)
                branch_names = [
                    b.strip() for b in branch_matches if b.strip() and not b.startswith("tag:")
                ]

            commit_data = {
                "sha": sha,
                "parents": parents,
                "author_name": parts[2],
                "author_email": parts[3],
                "date": parts[4],
                "message": parts[5],
                "branches": branch_names,
            }
            commits.append(commit_data)

            # Track branch heads
            for branch in branch_names:
                if branch not in branches or sha not in [c["sha"] for c in commits]:
                    branches[branch] = sha

        return {"success": True, "commits": commits, "branches": branches}

    def git_list_branches(
        self, container_id: str, include_remote: bool = False
    ) -> dict[str, object]:
        """
        List all branches.
        """
        cmd = "git branch --list"
        if include_remote:
            cmd += " -a"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        branches = []
        current = None
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("*"):
                current = line[1:].strip()
                branches.append({"name": current, "current": True})
            else:
                name = (
                    line.replace("remotes/", "").replace("origin/", "") if include_remote else line
                )
                if name not in [b["name"] for b in branches]:
                    branches.append({"name": name, "current": False})

        return {"success": True, "branches": branches, "current": current}

    def git_create_branch(
        self, container_id: str, branch_name: str, start_point: str | None = None
    ) -> dict[str, str]:
        """
        Create a new branch.
        """
        safe_name = shlex.quote(branch_name)
        if start_point:
            cmd = f"git branch {safe_name} {shlex.quote(start_point)}"
        else:
            cmd = f"git branch {safe_name}"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_checkout_branch(
        self, container_id: str, branch_name: str, create: bool = False
    ) -> dict[str, str]:
        """
        Switch to a branch.
        """
        safe_name = shlex.quote(branch_name)
        if create:
            cmd = f"git checkout -b {safe_name}"
        else:
            cmd = f"git checkout {safe_name}"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_delete_branch(
        self,
        container_id: str,
        branch_name: str,
        force: bool = False,
        token: str | None = None,
        delete_remote: bool = True,
    ) -> dict[str, str]:
        """
        Delete a branch (local and optionally remote).
        Prevents deletion of the current branch.

        Args:
            container_id: Container ID
            branch_name: Branch name to delete
            force: Force delete (use -D instead of -d)
            token: GitHub token for deleting remote branch
            delete_remote: If True, also delete the remote branch (default: True)
        """
        # Check if this is the current branch
        current_branch_result = self.git_current_branch(container_id)
        current_branch = (
            current_branch_result.get("branch") if current_branch_result.get("success") else None
        )

        if current_branch == branch_name:
            return {
                "success": False,
                "error": f"Cannot delete the current branch '{branch_name}'. Please switch to another branch first.",
            }

        safe_name = shlex.quote(branch_name)
        flags = "-D" if force else "-d"
        cmd = f"git branch {flags} {safe_name}"

        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            # Provide more helpful error messages
            error_msg = output.strip() if output else "Unknown error"
            if "not found" in error_msg.lower():
                return {"success": False, "error": f"Branch '{branch_name}' not found"}
            elif "not fully merged" in error_msg.lower() and not force:
                return {
                    "success": False,
                    "error": f"Branch '{branch_name}' is not fully merged. Use force delete to delete it anyway.",
                }

        # Delete remote branch if requested and token is provided
        remote_deleted = False
        if delete_remote and token:
            remote_url = self._get_remote_url(container_id)
            if remote_url:
                # Update remote URL with token
                auth_url = self._inject_token(remote_url, token)
                set_result = self.git_set_remote_url(container_id, auth_url)
                if set_result.get("success"):
                    # Check if remote branch exists
                    check_cmd = f"git ls-remote --heads origin {safe_name}"
                    check_exit, check_output = self._exec(container_id, check_cmd)
                    if check_exit == 0 and check_output.strip():
                        # Remote branch exists, delete it
                        delete_remote_cmd = f"git push origin --delete {safe_name}"
                        remote_exit, remote_output = self._exec(container_id, delete_remote_cmd)
                        if remote_exit == 0:
                            remote_deleted = True
                            logger.info(f"Deleted remote branch '{branch_name}'")
                        else:
                            logger.warning(
                                f"Failed to delete remote branch '{branch_name}': {remote_output}"
                            )
                    else:
                        logger.info(
                            f"Remote branch '{branch_name}' does not exist, skipping remote deletion"
                        )
                else:
                    logger.warning(
                        f"Failed to update remote URL for branch deletion: {set_result.get('error')}"
                    )

        return {"success": True, "output": output, "remote_deleted": remote_deleted}

    def git_check_conflicts(self, container_id: str) -> dict[str, object]:
        """
        Check for merge conflicts.
        """
        cmd = "git diff --check"
        exit_code, output = self._exec(container_id, cmd)

        # Also check git status for conflict markers
        status_cmd = "git status --porcelain=v1"
        status_exit, status_output = self._exec(container_id, status_cmd)

        conflicts = []
        if status_exit == 0:
            for line in status_output.splitlines():
                if len(line) >= 2:
                    index_status = line[0]
                    worktree_status = line[1]
                    if index_status in {"U", "A", "D", "M"} and worktree_status in {
                        "U",
                        "A",
                        "D",
                        "M",
                    }:
                        file_path = line[3:].strip()
                        conflicts.append(file_path)

        return {"success": True, "has_conflicts": len(conflicts) > 0, "conflicts": conflicts}

    def git_get_conflict_content(self, container_id: str, file_path: str) -> dict[str, str]:
        """
        Get conflict content for a file.
        """
        safe_path = shlex.quote(file_path)
        cmd = f"cat {safe_path}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "content": output}

    def git_resolve_conflict(
        self, container_id: str, file_path: str, content: str, side: str = "ours"
    ) -> dict[str, str]:
        """
        Resolve a conflict by writing resolved content.
        side: "ours", "theirs", or "both" (manual resolution)
        """
        safe_path = shlex.quote(file_path)

        if side == "ours":
            cmd = f"git checkout --ours {safe_path}"
            exit_code, output = self._exec(container_id, cmd)
            if exit_code != 0:
                return {"success": False, "error": output}
        elif side == "theirs":
            cmd = f"git checkout --theirs {safe_path}"
            exit_code, output = self._exec(container_id, cmd)
            if exit_code != 0:
                return {"success": False, "error": output}
        elif side == "both":
            # Write the manually resolved content
            # We'll need to write this to the file in the container
            # For now, return error - this should be handled via file write API
            return {
                "success": False,
                "error": "Manual resolution should be done via file write API",
            }

        # Stage the resolved file
        add_cmd = f"git add {safe_path}"
        exit_code, output = self._exec(container_id, add_cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        return {"success": True, "output": output}

    def git_check_uncommitted(self, container_id: str) -> dict[str, object]:
        """
        Check for uncommitted changes.
        """
        cmd = "git status --porcelain=v1"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        files = [line[3:].strip() for line in output.splitlines() if line.strip()]
        return {"success": True, "has_changes": len(files) > 0, "files": files}

    def git_reset_hard(self, container_id: str, commit: str) -> dict[str, str]:
        """
        Hard reset to a commit.
        """
        cmd = f"git reset --hard {shlex.quote(commit)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}
        return {"success": True, "output": output}

    def git_ls_remote(self, container_id: str, remote: str, branch: str) -> dict[str, str]:
        """
        Get remote SHA for a branch.
        """
        cmd = f"git ls-remote {shlex.quote(remote)} {shlex.quote(branch)}"
        exit_code, output = self._exec(container_id, cmd)
        if exit_code != 0:
            return {"success": False, "error": output}

        sha = output.split()[0] if output.strip() else ""
        return {"success": True, "sha": sha}

    def configure_git_user(self, container_id: str, name: str, email: str) -> dict[str, str]:
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

    def git_merge(
        self,
        container_id: str,
        branch: str,
        no_ff: bool = False,
        message: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, object]:
        """
        Merge a branch into the current branch.

        Args:
            container_id: Container ID
            branch: Branch name to merge into current branch
            no_ff: Create merge commit even if fast-forward is possible
            message: Merge commit message (optional)
            author_name: Author name for merge commit (optional)
            author_email: Author email for merge commit (optional)

        Returns:
            Dict with success status, output, and conflict information
        """
        branch = branch.strip()
        if not branch:
            return {"success": False, "error": "Branch name is required"}

        # Check if branch exists
        branch_check = self.git_list_branches(container_id, include_remote=False)
        if not branch_check.get("success"):
            return {"success": False, "error": "Failed to list branches"}

        branch_names = [b.get("name") for b in branch_check.get("branches", [])]
        if branch not in branch_names:
            return {"success": False, "error": f"Branch '{branch}' not found"}

        # Check for uncommitted changes
        uncommitted = self.git_check_uncommitted(container_id)
        if not uncommitted.get("success"):
            return {"success": False, "error": "Failed to check uncommitted changes"}

        if uncommitted.get("has_changes"):
            return {
                "success": False,
                "error": "You have uncommitted changes. Please commit or stash them before merging.",
                "has_conflicts": False,
            }

        # Build merge command
        flags = []
        if no_ff:
            flags.append("--no-ff")
        else:
            flags.append("--ff")  # Allow fast-forward

        if message:
            flags.append(f"-m {shlex.quote(message)}")

        merge_cmd = f"git merge {' '.join(flags)} {shlex.quote(branch)}"

        # Set author if provided
        if author_name and author_email:
            env_prefix = self._author_env(author_name, author_email)
            merge_cmd = f"{env_prefix}{merge_cmd}"

        exit_code, output = self._exec(container_id, merge_cmd)

        # Check for conflicts
        if exit_code != 0:
            # Check if it's a conflict
            conflicts_result = self.git_check_conflicts(container_id)
            has_conflicts = (
                conflicts_result.get("has_conflicts", False)
                if conflicts_result.get("success")
                else False
            )

            if has_conflicts:
                return {
                    "success": False,
                    "error": "Merge conflicts detected",
                    "has_conflicts": True,
                    "conflicts": conflicts_result.get("conflicts", []),
                    "output": output,
                }
            else:
                return {
                    "success": False,
                    "error": output or "Merge failed",
                    "has_conflicts": False,
                }

        # Check for conflicts even if exit code is 0 (sometimes git returns 0 but has conflicts)
        conflicts_result = self.git_check_conflicts(container_id)
        has_conflicts = (
            conflicts_result.get("has_conflicts", False)
            if conflicts_result.get("success")
            else False
        )

        if has_conflicts:
            return {
                "success": False,
                "error": "Merge conflicts detected",
                "has_conflicts": True,
                "conflicts": conflicts_result.get("conflicts", []),
                "output": output,
            }

        return {
            "success": True,
            "output": output,
            "has_conflicts": False,
        }

    def git_abort_merge(self, container_id: str) -> dict[str, str]:
        """
        Abort an ongoing merge.

        Args:
            container_id: Container ID

        Returns:
            Dict with success status and output
        """
        # Check if there's an ongoing merge
        status_result = self.git_status(container_id)
        if not status_result.get("success"):
            return {"success": False, "error": "Failed to check git status"}

        conflicts = status_result.get("conflicts", [])
        if not conflicts:
            # Check if we're in a merge state
            exit_code, output = self._exec(container_id, "git rev-parse -q --verify MERGE_HEAD")
            if exit_code != 0:
                return {"success": False, "error": "No merge in progress"}

        cmd = "git merge --abort"
        exit_code, output = self._exec(container_id, cmd)

        if exit_code != 0:
            return {"success": False, "error": output or "Failed to abort merge"}

        return {"success": True, "output": output}

    def _exec(self, container_id: str, command: str) -> tuple[int, str]:
        return self._docker.exec_command(container_id, command, workdir="/workspace")

    def _get_remote_url(self, container_id: str) -> str | None:
        exit_code, output = self._exec(container_id, "git remote get-url origin")
        if exit_code != 0:
            return None
        return output.strip()

    @staticmethod
    def _author_env(author_name: str | None, author_email: str | None) -> str:
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
        First strips any existing auth from the URL (handles multiple @ signs).
        """
        token = token.strip()
        # Extract protocol
        if repo_url.startswith("https://"):
            protocol = "https://"
            rest = repo_url[8:]  # Remove "https://"
        elif repo_url.startswith("http://"):
            protocol = "http://"
            rest = repo_url[7:]  # Remove "http://"
        else:
            return repo_url

        # Find where the actual domain starts (after the last @ before the first /)
        # Example: old@x-access-token:old@github.com/path -> github.com/path
        if "/" in rest:
            # Find the last @ before the first /
            domain_and_auth, path = rest.split("/", 1)
            # Extract domain (everything after the last @)
            if "@" in domain_and_auth:
                domain = domain_and_auth.split("@")[-1]
            else:
                domain = domain_and_auth
            full_path = "/" + path
        else:
            # No path, just domain and auth
            if "@" in rest:
                domain = rest.split("@")[-1]
            else:
                domain = rest
            full_path = ""

        # Remove trailing slash from path (git doesn't like it)
        full_path = full_path.rstrip("/")
        # Don't URL-encode the token - GitHub tokens are designed to be used as-is in URLs
        return f"{protocol}x-access-token:{token}@{domain}{full_path}"

    @staticmethod
    def _redact_token(repo_url: str) -> str:
        return re.sub(r"(https?://)([^@]+)@", r"\1***@", repo_url)

    @staticmethod
    def _parse_branch_info(line: str) -> dict[str, object]:
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
