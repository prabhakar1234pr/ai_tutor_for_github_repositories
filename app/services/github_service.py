import asyncio
import base64
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# -----------------------------
# Configuration
# -----------------------------

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".r",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".md",
    ".markdown",
    ".txt",
    ".mdx",
    ".rst",
    ".tex",
}

IGNORE_PATTERNS = {
    ".git",
    ".github",
    ".vscode",
    ".idea",
    "__pycache__",
    "node_modules",
    ".next",
    ".nuxt",
    "dist",
    "build",
    ".venv",
    "venv",
    "env",
    ".env",
    ".ds_store",
}

BASENAME_ALLOWLIST = {"dockerfile", "makefile"}

EXTENSION_LANGUAGE_MAP = {
    "py": "python",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "md": "markdown",
    "json": "json",
    "yml": "yaml",
    "yaml": "yaml",
    "html": "html",
    "css": "css",
    "go": "go",
    "rs": "rust",
    "java": "java",
}

# Max concurrent GitHub blob fetches (increased for better performance)
FETCH_SEMAPHORE = asyncio.Semaphore(20)


# -----------------------------
# Helpers
# -----------------------------


def extract_repo_info(github_url: str) -> tuple[str, str]:
    patterns = [
        r"github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
        r"github\.com/([^/]+)/([^/]+?)/.*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, github_url)
        if match:
            return match.group(1), match.group(2)

    raise ValueError(f"Invalid GitHub URL: {github_url}")


def should_ignore_file(file_path: str) -> bool:
    path = file_path.lower()

    for pattern in IGNORE_PATTERNS:
        if pattern in path:
            return True

    filename = path.split("/")[-1]

    if filename in BASENAME_ALLOWLIST:
        return False

    if not any(path.endswith(ext) for ext in CODE_EXTENSIONS):
        return True

    return False


def detect_language(file_path: str) -> str:
    ext = file_path.split(".")[-1].lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "text")


async def fetch_blob(client: httpx.AsyncClient, url: str, headers: dict) -> str:
    async with FETCH_SEMAPHORE:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")


# -----------------------------
# Main API
# -----------------------------


async def fetch_repository_files(github_url: str) -> list[dict[str, str]]:
    """
    Fetch code/text files from a GitHub repository with safety limits.

    Returns:
        [
          {
            "file_path": str,
            "content": str,
            "language": str
          }
        ]
    """
    owner, repo = extract_repo_info(github_url)
    logger.info(f"📂 Fetching repository: {owner}/{repo} from {github_url}")

    headers = {}
    if settings.git_access_token:
        headers["Authorization"] = f"token {settings.git_access_token}"
        logger.debug("🔑 Using GitHub access token for authentication")
    else:
        logger.warning("⚠️  No GitHub access token configured, using unauthenticated requests")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # -----------------------------
        # Get default branch
        # -----------------------------
        logger.debug("🌿 Fetching repository info to get default branch")
        repo_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}", headers=headers
        )
        repo_resp.raise_for_status()
        default_branch = repo_resp.json()["default_branch"]
        logger.info(f"✅ Default branch: {default_branch}")

        # -----------------------------
        # Fetch repository tree
        # -----------------------------
        logger.debug(f"🌳 Fetching repository tree (recursive) for branch: {default_branch}")
        tree_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
            headers=headers,
        )
        tree_resp.raise_for_status()
        tree_data = tree_resp.json()
        total_items = len(tree_data.get("tree", []))
        logger.info(f"📋 Repository tree contains {total_items} items")

        files: list[dict[str, str]] = []
        total_bytes = 0
        skipped_count = 0
        large_file_count = 0

        max_files = settings.max_files_per_project
        max_bytes = int(settings.max_text_size_mb * 1024 * 1024)
        logger.debug(f"📊 Limits: max_files={max_files}, max_size={max_bytes / 1024 / 1024:.1f} MB")

        tasks = []

        for item in tree_data.get("tree", []):
            if item["type"] != "blob":
                continue

            file_path = item["path"]

            if should_ignore_file(file_path):
                skipped_count += 1
                logger.debug(f"⏭️  Skipping ignored file: {file_path}")
                continue

            file_size = item.get("size", 0)
            if file_size > 1024 * 1024:
                large_file_count += 1
                logger.debug(f"📦 Skipping large file ({file_size / 1024:.1f} KB): {file_path}")
                continue

            blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{item['sha']}"
            tasks.append((file_path, blob_url))

        logger.info(
            f"📥 Preparing to fetch {len(tasks)} files (skipped {skipped_count} ignored, {large_file_count} large files)"
        )

        # Optimize: Fetch files in parallel using asyncio.gather
        async def fetch_file_with_metadata(file_path: str, blob_url: str) -> dict[str, str] | None:
            """Fetch a single file and return its metadata.

            Important: do NOT raise here. If a single fetch raises and bubbles up,
            asyncio.gather() will cancel remaining tasks and the AsyncClient context
            may close while other tasks are still pending, causing the noisy cascade:
            "Cannot send a request, as the client has been closed."
            """
            try:
                content = await fetch_blob(client, blob_url, headers)
                language = detect_language(file_path)
                return {
                    "file_path": file_path,
                    "content": content,
                    "language": language,
                    "size_bytes": len(content.encode("utf-8")),
                }
            except Exception as e:
                logger.error(f"❌ Failed to fetch file {file_path}: {e}")
                return None

        # Fetch all files in parallel (respecting semaphore limit)
        logger.debug(f"🚀 Starting parallel fetch of {len(tasks)} files")
        fetch_tasks = [
            fetch_file_with_metadata(file_path, blob_url) for file_path, blob_url in tasks
        ]

        fetched_results = await asyncio.gather(*fetch_tasks, return_exceptions=False)

        # Process results and check limits
        for result in fetched_results:
            if result is None:
                continue
            content_bytes = result["size_bytes"]
            total_bytes += content_bytes

            if len(files) >= max_files:
                logger.error(
                    f"❌ Repository exceeds maximum file limit: {len(files)} >= {max_files}"
                )
                raise ValueError(f"Repository exceeds maximum file limit ({max_files} files)")

            if total_bytes > max_bytes:
                logger.error(
                    f"❌ Repository exceeds maximum text size: {total_bytes / 1024 / 1024:.2f} MB > {max_bytes / 1024 / 1024:.2f} MB"
                )
                raise ValueError(
                    f"Repository exceeds maximum text size ({max_bytes / 1024 / 1024:.1f} MB)"
                )

            files.append(
                {
                    "file_path": result["file_path"],
                    "content": result["content"],
                    "language": result["language"],
                }
            )

        logger.debug(
            f"✅ Parallel fetch completed: {len(files)} files ({total_bytes / 1024:.1f} KB)"
        )

        logger.info(
            f"✅ Successfully fetched {len(files)} files ({total_bytes / 1024:.1f} KB, {total_bytes / 1024 / 1024:.2f} MB)"
        )
        languages_set = {f["language"] for f in files}
        files_by_lang = {
            lang: sum(1 for f in files if f["language"] == lang) for lang in languages_set
        }
        logger.debug(f"   Files by language: {files_by_lang}")
        return files
