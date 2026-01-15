from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.utils.github_utils import extract_project_name, validate_github_url
from app.services.embedding_pipeline import run_embedding_pipeline
from app.services.qdrant_service import get_qdrant_service
from app.agents.day0 import get_day_0_content
from app.utils.markdown_sanitizer import sanitize_markdown_content
from supabase import Client
import logging
import time
from typing import Literal, Dict

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateProjectRequest(BaseModel):
    github_url: str = Field(..., description="GitHub repository URL")
    skill_level: Literal["beginner", "intermediate", "advanced"] = Field(..., description="User's skill level")
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
        
        # Initialize Day 0 content immediately
        try:
            # Call the Day 0 initialization logic directly
            await _initialize_day0_internal(str(project_id), user_id, supabase)
        except Exception as e:
            logger.error(f"❌ Error initializing Day 0: {e}", exc_info=True)
            # Don't fail project creation if Day 0 fails - it can be retried
        
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


async def _initialize_day0_internal(project_id: str, user_id: str, supabase: Client):
    """
    Internal function to initialize Day 0 content.
    Can be called from project creation or as a standalone endpoint.
    """
    logger.info(f"📝 Initializing Day 0 content for project_id={project_id}")
    
    # Verify project exists and belongs to the user
    project_response = supabase.table("Projects").select("*").eq("project_id", project_id).eq("user_id", user_id).execute()
    
    if not project_response.data or len(project_response.data) == 0:
        raise ValueError("Project not found or you don't have permission")
    
    project = project_response.data[0]
    project_status = project.get("status")
    
    # Check if project is in valid status
    if project_status not in ["created", "processing"]:
        raise ValueError(f"Project must be in 'created' or 'processing' status. Current status: {project_status}")
    
    # Check if Day 0 already exists
    day0_response = (
        supabase.table("roadmap_days")
        .select("day_id, day_number, generated_status")
        .eq("project_id", project_id)
        .eq("day_number", 0)
        .execute()
    )
    
    day0_id = None
    if day0_response.data and len(day0_response.data) > 0:
        day0_id = day0_response.data[0]["day_id"]
        generated_status = day0_response.data[0].get("generated_status")
        
        if generated_status == "generated":
            logger.info(f"✅ Day 0 already generated for project {project_id}")
            return {
                "success": True,
                "message": "Day 0 already initialized",
                "day0_id": day0_id,
                "already_exists": True
            }
    
    # Insert Day 0 into roadmap_days if not exists
    if not day0_id:
        day0_theme, _ = get_day_0_content()
        day0_insert = {
            "project_id": project_id,
            "day_number": 0,
            "theme": day0_theme["theme"],
            "description": day0_theme["description"],
            "estimated_minutes": 30,
            "generated_status": "pending",
        }
        
        day0_insert_response = supabase.table("roadmap_days").insert(day0_insert).execute()
        
        if not day0_insert_response.data:
            raise ValueError("Failed to insert Day 0 into roadmap_days")
        
        day0_id = day0_insert_response.data[0]["day_id"]
        logger.info(f"✅ Inserted Day 0 into roadmap_days: {day0_id}")
    
    # Get Day 0 content
    _, day0_concepts = get_day_0_content()
    
    # Insert concepts with content field
    concepts_to_insert = []
    for concept in day0_concepts:
        raw_content = concept.get("content", "")
        sanitized_content = sanitize_markdown_content(raw_content)
        concepts_to_insert.append({
            "day_id": day0_id,
            "order_index": concept["order_index"],
            "title": concept["title"],
            "description": concept["description"],
            "content": sanitized_content,
            "estimated_minutes": concept.get("estimated_minutes", 10),
            "generated_status": "generated",
        })
    
    concepts_response = supabase.table("concepts").insert(concepts_to_insert).execute()
    
    if not concepts_response.data:
        raise ValueError("Failed to insert Day 0 concepts")
    
    logger.info(f"✅ Inserted {len(concepts_response.data)} concepts for Day 0")
    
    # Create mapping: order_index -> concept_id
    concept_ids_map: Dict[int, str] = {}
    for concept_data in concepts_response.data:
        order_idx = concept_data["order_index"]
        concept_id = concept_data["concept_id"]
        concept_ids_map[order_idx] = concept_id
    
    # Insert tasks for each concept
    total_tasks = 0
    for concept in day0_concepts:
        concept_id = concept_ids_map[concept["order_index"]]
        
        if concept.get("tasks"):
            tasks_to_insert = []
            for task in concept["tasks"]:
                tasks_to_insert.append({
                    "concept_id": concept_id,
                    "order_index": task["order_index"],
                    "title": task["title"],
                    "description": task["description"],
                    "task_type": task["task_type"],
                    "estimated_minutes": task.get("estimated_minutes", 15),
                    "difficulty": task.get("difficulty", "medium"),
                    "hints": task.get("hints", []),
                    "solution": task.get("solution"),
                    "generated_status": "generated",
                })
            
            supabase.table("tasks").insert(tasks_to_insert).execute()
            total_tasks += len(tasks_to_insert)
            logger.debug(f"   Inserted {len(tasks_to_insert)} tasks for concept {concept['title']}")
    
    # Mark Day 0 as generated
    supabase.table("roadmap_days").update({
        "generated_status": "generated"
    }).eq("day_id", day0_id).execute()
    
    logger.info(f"✅ Day 0 content initialized successfully: {len(concepts_response.data)} concepts, {total_tasks} tasks")
    
    return {
        "success": True,
        "message": "Day 0 initialized successfully",
        "day0_id": day0_id,
        "concepts_count": len(concepts_response.data),
        "tasks_count": total_tasks,
        "already_exists": False
    }


@router.post("/{project_id}/initialize-day0")
async def initialize_day0_content(
    project_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Initialize Day 0 content for a project.
    This endpoint should be called when a project is created or in processing phase.
    
    Flow:
    1. Verify project exists and belongs to user
    2. Check project status (must be "created" or "processing")
    3. Check if Day 0 already exists
    4. Insert Day 0 into roadmap_days if not exists
    5. Generate and save Day 0 content (concepts and tasks)
    6. Mark Day 0 as generated
    
    Returns:
        dict with success status and details
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Call internal function
        result = await _initialize_day0_internal(project_id, user_id, supabase)
        
        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error initializing Day 0: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to initialize Day 0: {str(e)}")
    """
    Initialize Day 0 content for a project.
    This endpoint should be called when a project is created or in processing phase.
    
    Flow:
    1. Verify project exists and belongs to user
    2. Check project status (must be "created" or "processing")
    3. Check if Day 0 already exists
    4. Insert Day 0 into roadmap_days if not exists
    5. Generate and save Day 0 content (concepts and tasks)
    6. Mark Day 0 as generated
    
    Returns:
        dict with success status and details
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        
        logger.info(f"📝 Initializing Day 0 content for project_id={project_id}")
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project exists and belongs to the user
        project_response = supabase.table("Projects").select("*").eq("project_id", project_id).eq("user_id", user_id).execute()
        
        if not project_response.data or len(project_response.data) == 0:
            raise HTTPException(status_code=404, detail="Project not found or you don't have permission")
        
        project = project_response.data[0]
        project_status = project.get("status")
        
        # Check if project is in valid status
        if project_status not in ["created", "processing"]:
            raise HTTPException(
                status_code=400,
                detail=f"Project must be in 'created' or 'processing' status. Current status: {project_status}"
            )
        
        # Check if Day 0 already exists
        day0_response = (
            supabase.table("roadmap_days")
            .select("day_id, day_number, generated_status")
            .eq("project_id", project_id)
            .eq("day_number", 0)
            .execute()
        )
        
        day0_id = None
        if day0_response.data and len(day0_response.data) > 0:
            day0_id = day0_response.data[0]["day_id"]
            generated_status = day0_response.data[0].get("generated_status")
            
            if generated_status == "generated":
                logger.info(f"✅ Day 0 already generated for project {project_id}")
                return {
                    "success": True,
                    "message": "Day 0 already initialized",
                    "day0_id": day0_id,
                    "already_exists": True
                }
        
        # Insert Day 0 into roadmap_days if not exists
        if not day0_id:
            day0_theme, _ = get_day_0_content()
            day0_insert = {
                "project_id": project_id,
                "day_number": 0,
                "theme": day0_theme["theme"],
                "description": day0_theme["description"],
                "estimated_minutes": 30,
                "generated_status": "pending",
            }
            
            day0_insert_response = supabase.table("roadmap_days").insert(day0_insert).execute()
            
            if not day0_insert_response.data:
                raise HTTPException(status_code=500, detail="Failed to insert Day 0 into roadmap_days")
            
            day0_id = day0_insert_response.data[0]["day_id"]
            logger.info(f"✅ Inserted Day 0 into roadmap_days: {day0_id}")
        
        # Get Day 0 content
        _, day0_concepts = get_day_0_content()
        
        # Insert concepts with content field
        concepts_to_insert = []
        for concept in day0_concepts:
            raw_content = concept.get("content", "")
            sanitized_content = sanitize_markdown_content(raw_content)
            concepts_to_insert.append({
                "day_id": day0_id,
                "order_index": concept["order_index"],
                "title": concept["title"],
                "description": concept["description"],
                "content": sanitized_content,
                "estimated_minutes": concept.get("estimated_minutes", 10),
                "generated_status": "generated",
            })
        
        concepts_response = supabase.table("concepts").insert(concepts_to_insert).execute()
        
        if not concepts_response.data:
            raise HTTPException(status_code=500, detail="Failed to insert Day 0 concepts")
        
        logger.info(f"✅ Inserted {len(concepts_response.data)} concepts for Day 0")
        
        # Create mapping: order_index -> concept_id
        concept_ids_map: Dict[int, str] = {}
        for concept_data in concepts_response.data:
            order_idx = concept_data["order_index"]
            concept_id = concept_data["concept_id"]
            concept_ids_map[order_idx] = concept_id
        
        # Insert tasks for each concept
        total_tasks = 0
        for concept in day0_concepts:
            concept_id = concept_ids_map[concept["order_index"]]
            
            if concept.get("tasks"):
                tasks_to_insert = []
                for task in concept["tasks"]:
                    tasks_to_insert.append({
                        "concept_id": concept_id,
                        "order_index": task["order_index"],
                        "title": task["title"],
                        "description": task["description"],
                        "task_type": task["task_type"],
                        "estimated_minutes": task.get("estimated_minutes", 15),
                        "difficulty": task.get("difficulty", "medium"),
                        "hints": task.get("hints", []),
                        "solution": task.get("solution"),
                        "generated_status": "generated",
                    })
                
                supabase.table("tasks").insert(tasks_to_insert).execute()
                total_tasks += len(tasks_to_insert)
                logger.debug(f"   Inserted {len(tasks_to_insert)} tasks for concept {concept['title']}")
        
        # Mark Day 0 as generated
        supabase.table("roadmap_days").update({
            "generated_status": "generated"
        }).eq("day_id", day0_id).execute()
        
        logger.info(f"✅ Day 0 content initialized successfully: {len(concepts_response.data)} concepts, {total_tasks} tasks")
        
        return {
            "success": True,
            "message": "Day 0 initialized successfully",
            "day0_id": day0_id,
            "concepts_count": len(concepts_response.data),
            "tasks_count": total_tasks,
            "already_exists": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing Day 0: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to initialize Day 0: {str(e)}")


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