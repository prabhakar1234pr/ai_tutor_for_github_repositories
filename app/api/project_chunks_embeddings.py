from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.embedding_pipeline import run_embedding_pipeline

router = APIRouter(
    prefix="/projects/chunks-embeddings",
    tags=["Project Chunks & Embeddings"],
)


class ChunkEmbeddingRequest(BaseModel):
    project_id: UUID
    github_url: str


@router.post("/run")
async def start_project_embedding(
    payload: ChunkEmbeddingRequest,
    background_tasks: BackgroundTasks,
    supabase: Client = Depends(get_supabase_client),
):
    """
    Kick off the embedding pipeline for a project in the background.
    """
    project_response = (
        supabase.table("projects")
        .select("project_id, github_url, status")
        .eq("project_id", str(payload.project_id))
        .execute()
    )

    if not project_response.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_response.data[0]

    # Ensure the GitHub URL matches or is stored
    stored_url = project.get("github_url")
    if stored_url and stored_url != payload.github_url:
        raise HTTPException(
            status_code=400,
            detail="Provided GitHub URL does not match stored project URL",
        )

    if project.get("status") == "processing":
        raise HTTPException(
            status_code=409,
            detail="Embedding pipeline is already running for this project",
        )

    # Schedule the async pipeline; FastAPI will execute this after response returns.
    background_tasks.add_task(
        run_embedding_pipeline,
        str(payload.project_id),
        payload.github_url,
    )

    return {
        "success": True,
        "message": "Embedding pipeline started",
        "project_id": str(payload.project_id),
    }


@router.get("/{project_id}/status")
async def get_project_embedding_status(
    project_id: UUID,
    supabase: Client = Depends(get_supabase_client),
):
    """
    Return the current embedding status for a project.
    """
    response = (
        supabase.table("projects")
        .select("project_id, status, error_message, updated_at")
        .eq("project_id", str(project_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = response.data[0]
    return {
        "project_id": project["project_id"],
        "status": project["status"],
        "error_message": project.get("error_message"),
        "updated_at": project.get("updated_at"),
    }


@router.get("/{project_id}/chunks")
async def list_project_chunks(
    project_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
):
    """
    List stored chunks for a project (metadata + content).
    """
    # Verify project exists
    project_resp = (
        supabase.table("projects").select("project_id").eq("project_id", str(project_id)).execute()
    )
    if not project_resp.data:
        raise HTTPException(status_code=404, detail="Project not found")

    chunks_resp = (
        supabase.table("project_chunks")
        .select("id, file_path, chunk_index, language, content, token_count, created_at")
        .eq("project_id", str(project_id))
        .order("file_path")
        .order("chunk_index")
        .range(offset, offset + limit - 1)
        .execute()
    )

    return {
        "project_id": str(project_id),
        "count": len(chunks_resp.data) if chunks_resp.data else 0,
        "chunks": chunks_resp.data or [],
    }
