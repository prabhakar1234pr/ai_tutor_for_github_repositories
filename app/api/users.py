import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/sync")
async def sync_user(
    user_info: dict = Depends(verify_clerk_token), supabase: Client = Depends(get_supabase_client)
):
    """
    Sync Clerk user to Supabase User table

    Flow:
    1. Verify token (via verify_clerk_token dependency)
    2. Check if user exists in Supabase
    3. If exists → update
    4. If not → create
    5. Return user data
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        email = user_info.get("email")
        name = user_info.get("name")

        logger.info(f"Syncing user: {clerk_user_id}")

        # Check if user exists
        existing_user_response = (
            supabase.table("User").select("*").eq("clerk_user_id", clerk_user_id).execute()
        )

        if existing_user_response.data and len(existing_user_response.data) > 0:
            # Update existing user
            updated_user_response = (
                supabase.table("User")
                .update(
                    {
                        "email": email,
                        "name": name,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("clerk_user_id", clerk_user_id)
                .execute()
            )

            if not updated_user_response.data:
                raise HTTPException(status_code=500, detail="Failed to update user")

            logger.info(f"Updated user: {clerk_user_id}")
            return {"success": True, "user": updated_user_response.data[0], "action": "updated"}
        else:
            # Create new user
            new_user_response = (
                supabase.table("User")
                .insert(
                    {
                        "clerk_user_id": clerk_user_id,
                        "email": email,
                        "name": name,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                .execute()
            )

            if not new_user_response.data:
                raise HTTPException(status_code=500, detail="Failed to create user")

            logger.info(f"Created user: {clerk_user_id}")
            return {"success": True, "user": new_user_response.data[0], "action": "created"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to sync user: {str(e)}") from e


@router.get("/me")
async def get_current_user(
    user_info: dict = Depends(verify_clerk_token), supabase: Client = Depends(get_supabase_client)
):
    """
    Get current authenticated user from Supabase
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]

        user_response = (
            supabase.table("User").select("*").eq("clerk_user_id", clerk_user_id).execute()
        )

        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found in database")

        return {"success": True, "user": user_response.data[0]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}") from e
