from fastapi import HTTPException, Header
from typing import Optional
import httpx
import jwt
import logging
from app.config import settings

logger = logging.getLogger(__name__)

async def verify_clerk_token(authorization: Optional[str] = Header(None)) -> dict:
    """Validate Clerk JWT and return user info (id, email, name)."""

    # 1. Ensure Authorization header exists
    if not authorization:
        raise HTTPException(401, "Authorization header missing")

    # 2. Extract token from "Bearer <token>"
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header format")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Token missing")

    # 3. Ensure Clerk secret key is configured
    if not settings.clerk_secret_key:
        logger.error("Clerk secret key missing")
        raise HTTPException(500, "Authentication service not configured")

    # 4. Decode JWT (without verifying signature) to get user ID
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        clerk_user_id = decoded.get("sub")
        if not clerk_user_id:
            raise HTTPException(401, "Invalid token: user ID missing")
    except Exception:
        raise HTTPException(401, "Invalid token format")

    # 5. Fetch user from Clerk REST API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.clerk.com/v1/users/{clerk_user_id}",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"}
            )
    except httpx.TimeoutException:
        raise HTTPException(500, "Clerk service timeout")
    except Exception as e:
        logger.error(f"Clerk API error: {e}")
        raise HTTPException(500, "Failed to contact Clerk")

    # 6. Handle Clerk API errors
    if resp.status_code == 401:
        raise HTTPException(401, "Invalid Clerk API key")
    if resp.status_code == 404:
        raise HTTPException(401, "User not found")
    if resp.status_code != 200:
        logger.error(f"Clerk API error: {resp.status_code} - {resp.text}")
        raise HTTPException(500, "Failed to verify user with Clerk")

    user = resp.json()

    # 7. Extract email
    email = None
    emails = user.get("email_addresses", [])
    primary_id = user.get("primary_email_address_id")

    if emails:
        primary = next((e for e in emails if e["id"] == primary_id), emails[0])
        email = primary.get("email_address")

    # 8. Extract name
    first = user.get("first_name") or ""
    last = user.get("last_name") or ""
    name = (first + " " + last).strip() or user.get("username")

    return {
        "clerk_user_id": clerk_user_id,
        "email": email,
        "name": name
    }


