"""
GitHub Evidence Collector Service
Collects evidence from notebook repository via GitHub API for verification.
"""

import base64
import logging
from typing import Any

import httpx

from app.services.github_service import extract_repo_info

logger = logging.getLogger(__name__)


class GitHubEvidenceCollector:
    """
    Collects evidence from notebook repository (user_repo_url) via GitHub API.
    Used for baseline comparison during verification.
    """

    def __init__(self, github_token: str | None = None):
        self.github_token = github_token
        self.headers = {}
        if github_token:
            self.headers["Authorization"] = f"token {github_token}"

    async def get_repo_baseline(
        self, user_repo_url: str, file_paths: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Get baseline file contents from notebook repository.

        Args:
            user_repo_url: Notebook repository URL
            file_paths: Optional list of specific file paths to fetch

        Returns:
            {
                "files": {
                    "path/to/file.py": "file content...",
                    ...
                },
                "repo_structure": ["file1.py", "dir1/", ...],
                "default_branch": "main"
            }
        """
        try:
            owner, repo = extract_repo_info(user_repo_url)
        except Exception as e:
            logger.error(f"Failed to extract repo info from {user_repo_url}: {e}")
            return {"files": {}, "repo_structure": [], "default_branch": None}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Get default branch
                repo_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    headers=self.headers,
                )
                repo_resp.raise_for_status()
                repo_data = repo_resp.json()
                default_branch = repo_data.get("default_branch", "main")

                # Get repository tree
                tree_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
                    headers=self.headers,
                )
                tree_resp.raise_for_status()
                tree_data = tree_resp.json()

                # Build file structure
                repo_structure = []
                files_content = {}

                for item in tree_data.get("tree", []):
                    file_path = item.get("path", "")
                    item_type = item.get("type", "")

                    if item_type == "tree":
                        repo_structure.append(f"{file_path}/")
                    elif item_type == "blob":
                        repo_structure.append(file_path)

                        # Fetch file content if requested
                        if file_paths is None or file_path in file_paths:
                            blob_sha = item.get("sha")
                            if blob_sha:
                                blob_resp = await client.get(
                                    f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{blob_sha}",
                                    headers=self.headers,
                                )
                                blob_resp.raise_for_status()
                                blob_data = blob_resp.json()

                                if blob_data.get("encoding") == "base64":
                                    content = base64.b64decode(blob_data.get("content", "")).decode(
                                        "utf-8"
                                    )
                                    files_content[file_path] = content

                return {
                    "files": files_content,
                    "repo_structure": sorted(repo_structure),
                    "default_branch": default_branch,
                }

            except httpx.HTTPStatusError as e:
                logger.error(f"GitHub API error: {e.response.status_code} - {e.response.text}")
                return {"files": {}, "repo_structure": [], "default_branch": None}
            except Exception as e:
                logger.error(f"Failed to get repo baseline: {e}", exc_info=True)
                return {"files": {}, "repo_structure": [], "default_branch": None}

    async def compare_file_structure(
        self, user_repo_url: str, expected_files: list[str]
    ) -> dict[str, Any]:
        """
        Compare expected files with actual repository structure.

        Args:
            user_repo_url: Notebook repository URL
            expected_files: List of expected file paths

        Returns:
            {
                "missing_files": [str],
                "existing_files": [str],
                "all_exist": bool
            }
        """
        baseline = await self.get_repo_baseline(user_repo_url)
        repo_structure = set(baseline.get("repo_structure", []))

        missing_files = []
        existing_files = []

        for expected_file in expected_files:
            # Check if file exists (exact match or as directory)
            if expected_file in repo_structure or any(
                path.startswith(expected_file + "/") for path in repo_structure
            ):
                existing_files.append(expected_file)
            else:
                missing_files.append(expected_file)

        return {
            "missing_files": missing_files,
            "existing_files": existing_files,
            "all_exist": len(missing_files) == 0,
        }
