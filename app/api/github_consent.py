"""
GitHub Consent API
Handles GitHub PAT storage and consent management for projects.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from supabase import Client
import httpx
import logging
from datetime import datetime, timezone

from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import verify_project_and_get_user_id

router = APIRouter()
logger = logging.getLogger(__name__)


class GitHubConsentRequest(BaseModel):
    token: str = Field(..., description="GitHub Personal Access Token (PAT)")
    consent_accepted: bool = Field(..., description="Whether user accepted consent terms")
    github_username: str = Field(..., description="GitHub username")
    project_id: str = Field(..., description="Project ID")


class GitHubConsentResponse(BaseModel):
    success: bool
    message: str
    github_username: str


async def validate_github_token(token: str) -> dict:
    """
    Validate GitHub PAT by calling GitHub API.
    Returns user info if token is valid.
    
    Args:
        token: GitHub PAT
        
    Returns:
        dict with 'login' (username) and 'id' (user ID)
        
    Raises:
        HTTPException if token is invalid
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid GitHub token. Please check your Personal Access Token."
                )
            
            if response.status_code == 403:
                raise HTTPException(
                    status_code=403,
                    detail="GitHub token lacks required permissions. Ensure your PAT has 'Contents' read/write access."
                )
            
            if response.status_code != 200:
                logger.error(f"GitHub API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to validate GitHub token"
                )
            
            user_data = response.json()
            return {
                "login": user_data.get("login"),
                "id": user_data.get("id"),
                "name": user_data.get("name"),
                "email": user_data.get("email")
            }
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=500, detail="GitHub API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating GitHub token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate token: {str(e)}")


async def verify_token_has_repo_access(token: str, repo_url: str) -> bool:
    """
    Verify that the token has access to the specified repository.
    
    Args:
        token: GitHub PAT
        repo_url: Repository URL (e.g., https://github.com/username/repo)
        
    Returns:
        True if token has access, False otherwise
    """
    try:
        # Extract owner/repo from URL
        import re
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return False
            
        owner = match.group(1)
        repo = match.group(2).replace('.git', '')
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            return response.status_code == 200
            
    except Exception as e:
        logger.error(f"Error verifying repo access: {e}")
        return False


@router.post("/consent", response_model=GitHubConsentResponse)
async def store_github_consent(
    request: GitHubConsentRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Store GitHub PAT and consent for a project.
    
    Flow:
    1. Verify user authentication
    2. Verify project ownership
    3. Validate GitHub token
    4. Extract username from token (override with provided username if different)
    5. Verify token has access to project's repository (if user_repo_url exists)
    6. Store token, username, consent, and timestamp in projects table
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Verify project ownership and get project data
        user_id, project_data = verify_project_and_get_user_id(
            supabase,
            clerk_user_id,
            request.project_id,
            select_fields="project_id, github_username, user_repo_url"
        )
        
        logger.info(f"Storing GitHub consent for project {request.project_id}, user {user_id}")
        
        # Get stored username from Task 1 (source of truth)
        stored_username = project_data.get("github_username")
        if not stored_username:
            raise HTTPException(
                status_code=400,
                detail="GitHub username not found. Please complete Task 1 (Verify Your GitHub Profile) first."
            )
        
        # Validate GitHub token
        github_user_data = await validate_github_token(request.token)
        github_username_from_token = github_user_data.get("login")
        
        if not github_username_from_token:
            raise HTTPException(
                status_code=400,
                detail="Could not determine GitHub username from token"
            )
        
        # Validate username matches Task 1 username (source of truth)
        if github_username_from_token.lower() != stored_username.lower():
            raise HTTPException(
                status_code=403,
                detail=f"GitHub username mismatch. Token belongs to '@{github_username_from_token}', "
                       f"but Task 1 verified '@{stored_username}'. "
                       f"Please use a PAT token from the same GitHub account (@{stored_username})."
            )
        
        # Verify token has access to user's repository (Task 2)
        user_repo_url = project_data.get("user_repo_url")
        if not user_repo_url:
            raise HTTPException(
                status_code=400,
                detail="Repository URL not found. Please complete Task 2 (Create Your Project Repository) first."
            )
        
        has_access = await verify_token_has_repo_access(request.token, user_repo_url)
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail=f"Token does not have access to repository: {user_repo_url}. "
                       "Ensure your PAT is scoped to this repository with 'Contents' read/write permissions."
            )
        
        # Validate consent
        if not request.consent_accepted:
            raise HTTPException(
                status_code=400,
                detail="Consent must be accepted to continue"
            )
        
        # Store in projects table
        # Note: In production, encrypt the token before storing
        # For MVP, storing as-is (Supabase encryption at rest handles this)
        # Username is already stored from Task 1, so we don't overwrite it
        update_data = {
            "github_access_token": request.token,  # TODO: Encrypt before storing
            "github_consent_accepted": True,
            "github_consent_timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        result = (
            supabase.table("Projects")
            .update(update_data)
            .eq("project_id", request.project_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update project with GitHub consent"
            )
        
        logger.info(
            f"✅ GitHub consent stored for project {request.project_id}, "
            f"username: {stored_username} (validated against PAT token)"
        )
        
        return GitHubConsentResponse(
            success=True,
            message="GitHub account connected successfully",
            github_username=stored_username
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing GitHub consent: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to store GitHub consent: {str(e)}"
        )


@router.get("/consent/status")
async def get_consent_status(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get GitHub consent status for a project.
    
    Returns:
        {
            "has_consent": bool,
            "has_token": bool,
            "github_username": str | null,
            "consent_timestamp": str | null
        }
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Verify project ownership
        user_id, project_data = verify_project_and_get_user_id(
            supabase,
            clerk_user_id,
            project_id,
            select_fields="github_access_token, github_username, github_consent_accepted, github_consent_timestamp"
        )
        
        return {
            "has_consent": project_data.get("github_consent_accepted", False),
            "has_token": bool(project_data.get("github_access_token")),
            "github_username": project_data.get("github_username"),
            "consent_timestamp": project_data.get("github_consent_timestamp")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting consent status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get consent status: {str(e)}"
        )
