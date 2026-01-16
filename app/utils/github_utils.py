import re
from urllib.parse import urlparse


def extract_project_name(github_url: str) -> str:
    """
    Extract project name from GitHub URL

    Examples:
    - https://github.com/vercel/next.js -> next.js
    - https://github.com/facebook/react -> react
    - https://github.com/microsoft/vscode -> vscode
    """
    try:
        # Parse the URL
        parsed = urlparse(github_url)

        # Extract path (e.g., "/vercel/next.js")
        path = parsed.path.strip("/")

        # Split by '/' and get the last part (repository name)
        parts = path.split("/")

        if len(parts) >= 2:
            # Return repository name (last part)
            project_name = parts[-1]
            # Remove .git suffix if present
            project_name = project_name.replace(".git", "")
            return project_name
        else:
            raise ValueError("Invalid GitHub URL format")

    except Exception as e:
        raise ValueError(f"Failed to extract project name from URL: {str(e)}") from e


def validate_github_url(url: str) -> bool:
    """
    Validate if URL is a valid GitHub repository URL
    """
    github_pattern = r"^https?://(www\.)?github\.com/[\w\-\.]+/[\w\-\.]+/?$"
    return bool(re.match(github_pattern, url))
