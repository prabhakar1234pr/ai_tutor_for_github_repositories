from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.utils.github_utils import extract_project_name, validate_github_url
from supabase import Client
import logging
from typing import Literal

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateProjectRequest(BaseModel):
    github_url: str = Field(..., description="GitHub repository URL")
    skill_level: Literal["beginner", "intermediate", "expert"] = Field(..., description="User's skill level")
    target_days: int = Field(..., ge=7, le=30, description="Target duration in days (7-30)")
    
    @field_validator('github_url')
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        if not validate_github_url(v):
            raise ValueError("Invalid GitHub repository URL format")
        return v


@router.post("/create")
async def create_project(
    project_data: CreateProjectRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Create a new project in Supabase Projects table
    
    Flow:
    1. Verify Clerk token (get clerk_user_id)
    2. Get Supabase user_id from User table using clerk_user_id
    3. Extract project name from GitHub URL
    4. Validate input data
    5. Insert project into Projects table
    6. Return created project data
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        logger.info(f"Creating project for user: {clerk_user_id}")
        
        # Get Supabase user_id from User table
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(
                status_code=404, 
                detail="User not found in database. Please ensure you're logged in."
            )
        
        user_id = user_response.data[0]["id"]
        
        # Extract project name from GitHub URL
        try:
            project_name = extract_project_name(project_data.github_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Prepare project data
        project_insert = {
            "user_id": user_id,
            "project_name": project_name,
            "github_url": project_data.github_url,
            "skill_level": project_data.skill_level,
            "target_days": project_data.target_days,
            "status": "created"
        }
        
        logger.info(f"Inserting project: {project_name}")
        
        # Insert project into Projects table
        project_response = supabase.table("Projects").insert(project_insert).execute()
        
        if not project_response.data or len(project_response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create project")
        
        created_project = project_response.data[0]
        
        logger.info(f"Project created successfully: {created_project['project_id']}")
        
        return {
            "success": True,
            "project": {
                "project_id": created_project["project_id"],
                "project_name": created_project["project_name"],
                "github_url": created_project["github_url"],
                "skill_level": created_project["skill_level"],
                "target_days": created_project["target_days"],
                "status": created_project["status"],
                "created_at": created_project["created_at"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get project details by project_id
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Get project (ensure it belongs to the user)
        project_response = supabase.table("Projects").select("*").eq("project_id", project_id).eq("user_id", user_id).execute()
        
        if not project_response.data or len(project_response.data) == 0:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {
            "success": True,
            "project": project_response.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch project: {str(e)}")


@router.get("/user/list")
async def list_user_projects(
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    List all projects for the authenticated user
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Get all projects for user
        projects_response = supabase.table("Projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        return {
            "success": True,
            "projects": projects_response.data if projects_response.data else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing projects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")