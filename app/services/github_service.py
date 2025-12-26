import httpx
import logging
import re
import base64
import asyncio
from typing import List, Dict, Tuple
from app.config import settings

logger = logging.getLogger(__name__)

# -----------------------------
# Configuration
# -----------------------------

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".r",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".html", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".md", ".markdown",
    ".txt", ".mdx", ".rst", ".tex"
}

IGNORE_PATTERNS = {
    ".git", ".github", ".vscode", ".idea", "__pycache__",
    "node_modules", ".next", ".nuxt", "dist", "build",
    ".venv", "venv", "env", ".env", ".ds_store"
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

# Max concurrent GitHub blob fetches
FETCH_SEMAPHORE = asyncio.Semaphore(10)


# -----------------------------
# Helpers
# -----------------------------

def extract_repo_info(github_url: str) -> Tuple[str, str]:
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


async def fetch_blob(
    client: httpx.AsyncClient,
    url: str,
    headers: dict
) -> str:
    async with FETCH_SEMAPHORE:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")


# -----------------------------
# Main API
# -----------------------------

async def fetch_repository_files(github_url: str) -> List[Dict[str, str]]:
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
    logger.info(f"Fetching repository: {owner}/{repo}")

    headers = {}
    if settings.github_access_token:
        headers["Authorization"] = f"token {settings.github_access_token}"

    async with httpx.AsyncClient(timeout=30.0) as client:

        # -----------------------------
        # Get default branch
        # -----------------------------
        repo_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers
        )
        repo_resp.raise_for_status()
        default_branch = repo_resp.json()["default_branch"]

        # -----------------------------
        # Fetch repository tree
        # -----------------------------
        tree_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
            headers=headers
        )
        tree_resp.raise_for_status()
        tree_data = tree_resp.json()

        files: List[Dict[str, str]] = []
        total_bytes = 0

        max_files = settings.max_files_per_project
        max_bytes = int(settings.max_text_size_mb * 1024 * 1024)

        tasks = []

        for item in tree_data.get("tree", []):
            if item["type"] != "blob":
                continue

            file_path = item["path"]

            if should_ignore_file(file_path):
                continue

            if item.get("size", 0) > 1024 * 1024:
                logger.debug(f"Skipping large file: {file_path}")
                continue

            blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{item['sha']}"
            tasks.append((file_path, blob_url))

        for file_path, blob_url in tasks:
            content = await fetch_blob(client, blob_url, headers)
            content_bytes = len(content.encode("utf-8"))

            total_bytes += content_bytes

            if len(files) >= max_files:
                raise ValueError("Repository exceeds maximum file limit")

            if total_bytes > max_bytes:
                raise ValueError("Repository exceeds maximum text size")

            files.append({
                "file_path": file_path,
                "content": content,
                "language": detect_language(file_path)
            })

        logger.info(f"Fetched {len(files)} files ({total_bytes / 1024:.1f} KB)")
        return files
