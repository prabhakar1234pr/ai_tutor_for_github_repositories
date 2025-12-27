from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.utils.github_utils import extract_project_name, validate_github_url
from app.services.embedding_pipeline import run_embedding_pipeline
from app.services.qdrant_service import get_qdrant_service
from supabase import Client
import logging
import time
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
    background_tasks: BackgroundTasks,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Create a new project in Supabase Projects table and automatically start the embedding pipeline
    
    Flow:
    1. Verify Clerk token (get clerk_user_id)
    2. Get Supabase user_id from User table using clerk_user_id
    3. Extract project name from GitHub URL
    4. Validate input data
    5. Insert project into Projects table
    6. Trigger embedding pipeline in background
    7. Return created project data
    """
    api_start_time = time.time()
    
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        logger.info(f"⏱️  [TIMING] User clicked 'Let's start building' - API request received at {time.strftime('%Y-%m-%d %H:%M:%S')}")
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
        project_id = created_project['project_id']
        github_url = created_project['github_url']
        
        api_duration = time.time() - api_start_time
        logger.info(f"Project created successfully: {project_id}")
        logger.info(f"⏱️  [TIMING] API endpoint completed in {api_duration:.3f}s - Project inserted into database")
        
        # Trigger embedding pipeline in background
        # Pass the API start time to track total time from user click to completion
        background_tasks.add_task(
            run_embedding_pipeline,
            str(project_id),
            github_url,
            api_start_time,  # Pass API start time to pipeline
        )
        logger.info(f"⏱️  [TIMING] Background task scheduled - Pipeline will start processing")
        logger.info(f"Embedding pipeline scheduled for project: {project_id}")
        
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


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Delete a project and all associated data (chunks in Supabase, embeddings in Qdrant).
    
    Flow:
    1. Verify Clerk token (get clerk_user_id)
    2. Get Supabase user_id from User table using clerk_user_id
    3. Verify project exists and belongs to the user
    4. Delete embeddings from Qdrant
    5. Delete project from Supabase (chunks will cascade delete)
    6. Return deletion summary
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        logger.info(f"🗑️  Deleting project project_id={project_id} for user: {clerk_user_id}")
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project exists and belongs to the user
        project_response = supabase.table("Projects").select("*").eq("project_id", project_id).eq("user_id", user_id).execute()
        
        if not project_response.data or len(project_response.data) == 0:
            raise HTTPException(status_code=404, detail="Project not found or you don't have permission to delete it")
        
        project = project_response.data[0]
        project_name = project.get("project_name", "Unknown")
        
        logger.info(f"   Project found: {project_name} (project_id={project_id})")
        
        # Step 1: Delete embeddings from Qdrant
        qdrant_deleted_count = 0
        try:
            qdrant_service = get_qdrant_service()  # Use singleton for better performance
            qdrant_deleted_count = qdrant_service.delete_points_by_project_id(project_id)
            logger.info(f"✅ Deleted {qdrant_deleted_count} embeddings from Qdrant")
        except Exception as e:
            logger.warning(f"⚠️  Failed to delete embeddings from Qdrant (continuing with project deletion): {e}")
            # Continue with project deletion even if Qdrant deletion fails
        
        # Step 2: Delete project from Supabase (chunks will cascade delete)
        try:
            delete_response = supabase.table("Projects").delete().eq("project_id", project_id).eq("user_id", user_id).execute()
            logger.info(f"✅ Deleted project from Supabase (chunks cascaded)")
        except Exception as e:
            logger.error(f"❌ Failed to delete project from Supabase: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")
        
        logger.info(f"🎉 Successfully deleted project project_id={project_id}")
        
        return {
            "success": True,
            "message": "Project deleted successfully",
            "project_id": project_id,
            "project_name": project_name,
            "deleted_embeddings": qdrant_deleted_count,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")