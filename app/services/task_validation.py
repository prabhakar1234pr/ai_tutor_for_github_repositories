"""
Task validation service for automatically verifying task completion.
"""

import re
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


def validate_github_profile_url(url: str) -> bool:
    """
    Validate GitHub profile URL format.
    Example: https://github.com/username
    """
    pattern = r'^https?://github\.com/[a-zA-Z0-9]([a-zA-Z0-9]|-(?![.-])){0,38}/?$'
    return bool(re.match(pattern, url.strip()))


def validate_github_repo_url(url: str, expected_owner: Optional[str] = None) -> bool:
    """
    Validate GitHub repository URL format.
    Example: https://github.com/owner/repo
    """
    pattern = r'^https?://github\.com/([a-zA-Z0-9]([a-zA-Z0-9]|-(?![.-])){0,38})/([a-zA-Z0-9]([a-zA-Z0-9]|-(?![.-])){0,38})/?$'
    match = re.match(pattern, url.strip())
    if not match:
        return False
    
    if expected_owner:
        owner = match.group(1)
        return owner.lower() == expected_owner.lower()
    
    return True


def validate_github_commit_url(url: str, repo_url: Optional[str] = None) -> bool:
    """
    Validate GitHub commit URL or SHA format.
    Example: https://github.com/owner/repo/commit/abc123
    or just: abc123def456... (SHA)
    """
    # Check if it's a full URL
    if url.startswith('http'):
        pattern = r'^https?://github\.com/[a-zA-Z0-9]([a-zA-Z0-9]|-(?![.-])){0,38}/[a-zA-Z0-9]([a-zA-Z0-9]|-(?![.-])){0,38}/commit/[a-f0-9]{7,40}$'
        return bool(re.match(pattern, url.strip()))
    
    # Check if it's a SHA (7-40 hex characters)
    sha_pattern = r'^[a-f0-9]{7,40}$'
    return bool(re.match(sha_pattern, url.strip(), re.IGNORECASE))


async def validate_task_completion(
    task_type: str,
    task_data: Dict[str, Any],
    project_data: Optional[Dict[str, Any]] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate if a task is completed based on its type and provided data.
    
    Returns:
        (is_valid, error_message)
    """
    try:
        if task_type == 'github_profile':
            url = task_data.get('url', '').strip()
            if not url:
                return False, "GitHub profile URL is required"
            if not validate_github_profile_url(url):
                return False, "Invalid GitHub profile URL format"
            return True, None
        
        elif task_type == 'create_repo':
            url = task_data.get('url', '').strip()
            if not url:
                return False, "Repository URL is required"
            expected_owner = None
            if project_data and 'github_url' in project_data:
                # Extract owner from project's github_url
                match = re.search(r'github\.com/([^/]+)', project_data['github_url'])
                if match:
                    expected_owner = match.group(1)
            if not validate_github_repo_url(url, expected_owner):
                return False, "Invalid repository URL format or owner mismatch"
            return True, None
        
        elif task_type == 'verify_commit':
            url_or_sha = task_data.get('url', '').strip() or task_data.get('sha', '').strip()
            if not url_or_sha:
                return False, "Commit URL or SHA is required"
            if not validate_github_commit_url(url_or_sha):
                return False, "Invalid commit URL or SHA format"
            return True, None

        elif task_type == 'github_connect':
            # Token + consent are validated in github_consent endpoint
            return True, None
        
        elif task_type == 'coding':
            code = task_data.get('code', '').strip()
            if not code:
                return False, "Code is required"
            # Basic validation: code should have some content
            if len(code) < 10:
                return False, "Code seems too short. Please write more code."
            # Could add syntax checking here if needed
            return True, None
        
        elif task_type == 'reading':
            # Reading tasks are completed when user scrolls to end
            # This is handled in the frontend
            return True, None
        
        elif task_type == 'research':
            notes = task_data.get('notes', '').strip()
            resources = task_data.get('resources', [])
            if not notes and not resources:
                return False, "Please add notes or resources"
            if notes and len(notes) < 20:
                return False, "Please add more detailed notes"
            return True, None
        
        elif task_type == 'quiz':
            answers = task_data.get('answers', {})
            if not answers or len(answers) == 0:
                return False, "Please answer all questions"
            # Check if all answers have content
            for idx, answer in answers.items():
                if not answer or len(answer.strip()) < 5:
                    return False, f"Answer {idx} seems too short"
            return True, None
        
        else:
            logger.warning(f"Unknown task type: {task_type}")
            return False, f"Unknown task type: {task_type}"
    
    except Exception as e:
        logger.error(f"Error validating task: {e}", exc_info=True)
        return False, f"Validation error: {str(e)}"

