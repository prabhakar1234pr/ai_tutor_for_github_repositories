"""
Task Sessions API
Endpoints for base commit tracking per task session.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.task_session_service import TaskSessionService
from app.utils.clerk_auth import verify_clerk_token
from app.utils.db_helpers import get_user_id_from_clerk

router = APIRouter()
logger = logging.getLogger(__name__)


class StartSessionRequest(BaseModel):
    task_id: str
    workspace_id: str


class CompleteSessionRequest(BaseModel):
    current_commit: str | None = None


@router.post("/start")
def start_task_session(
    request: StartSessionRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    service = TaskSessionService(supabase=supabase)

    result = service.start_task_session(request.task_id, user_id, request.workspace_id)
    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Failed to start task session")
        )

    return result


@router.get("/{session_id}")
def get_task_session(
    session_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    service = TaskSessionService(supabase=supabase)

    session_result = service.get_session_by_id(session_id)
    if not session_result.get("success"):
        raise HTTPException(status_code=404, detail="Task session not found")
    session = session_result["session"]
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {"success": True, "session": session}


@router.post("/{session_id}/complete")
def complete_task_session(
    session_id: str,
    request: CompleteSessionRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    service = TaskSessionService(supabase=supabase)

    session_result = service.get_session_by_id(session_id)
    if not session_result.get("success"):
        raise HTTPException(status_code=404, detail="Task session not found")
    session = session_result["session"]
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = service.complete_task_session(session_id, current_commit=request.current_commit)
    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Failed to complete task session")
        )

    return result


@router.get("/{session_id}/diff")
def get_task_session_diff(
    session_id: str,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    user_id = get_user_id_from_clerk(supabase, user_info["clerk_user_id"])
    service = TaskSessionService(supabase=supabase)

    session_result = service.get_session_by_id(session_id)
    if not session_result.get("success"):
        raise HTTPException(status_code=404, detail="Task session not found")
    session = session_result["session"]
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = service.get_diff_for_verification(session_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to get diff"))

    return result
