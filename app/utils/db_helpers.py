"""
Database helper utilities for common operations.
Reduces code duplication across API endpoints.
"""

import logging
from typing import Any

from fastapi import HTTPException
from supabase import Client

logger = logging.getLogger(__name__)


def get_user_id_from_clerk(supabase: Client, clerk_user_id: str) -> str:
    """
    Get Supabase user_id from Clerk user_id.

    Args:
        supabase: Supabase client instance
        clerk_user_id: Clerk user ID

    Returns:
        Supabase user_id (UUID string)

    Raises:
        HTTPException: If user not found
    """
    user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()

    if not user_response.data or len(user_response.data) == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return user_response.data[0]["id"]


def verify_project_ownership(
    supabase: Client, project_id: str, user_id: str, select_fields: str | None = None
) -> dict[str, Any]:
    """
    Verify that a project exists and belongs to the user.

    Args:
        supabase: Supabase client instance
        project_id: Project UUID
        user_id: User UUID
        select_fields: Optional fields to select (default: "project_id")

    Returns:
        Project data dictionary

    Raises:
        HTTPException: If project not found or doesn't belong to user
    """
    fields = select_fields or "project_id"

    project_response = (
        supabase.table("Projects")
        .select(fields)
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not project_response.data or len(project_response.data) == 0:
        raise HTTPException(status_code=404, detail="Project not found")

    return project_response.data[0]


def verify_project_and_get_user_id(
    supabase: Client, clerk_user_id: str, project_id: str, select_fields: str | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Combined helper: Get user_id and verify project ownership in one call.
    More efficient than calling get_user_id_from_clerk + verify_project_ownership separately.

    Args:
        supabase: Supabase client instance
        clerk_user_id: Clerk user ID
        project_id: Project UUID
        select_fields: Optional fields to select from project

    Returns:
        Tuple of (user_id, project_data)

    Raises:
        HTTPException: If user or project not found
    """
    # Get user_id
    user_id = get_user_id_from_clerk(supabase, clerk_user_id)

    # Verify project ownership
    project_data = verify_project_ownership(supabase, project_id, user_id, select_fields)

    return user_id, project_data
