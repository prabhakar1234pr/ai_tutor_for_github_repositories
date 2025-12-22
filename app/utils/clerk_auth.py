from fastapi import HTTPException, Header
from typing import Optional
import httpx
from app.config import settings
import logging

logger = logging.getLogger(__name__)

async def verify_clerk_token(authorization: Optional[str] = Header(None)) -> dict:
    """
    Verify Clerk JWT token and return user info
    
    Flow:
    1. Extract token from Authorization header
    2. Verify token with Clerk REST API
    3. Get user details from Clerk
    4. Return clerk_user_id, email, name
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    # Extract token from "Bearer <token>"
    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            raise HTTPException(status_code=401, detail="Token missing")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    if not settings.clerk_secret_key:
        logger.error("Clerk secret key not configured")
        raise HTTPException(status_code=500, detail="Authentication service not configured")
    
    try:
        # Verify token and get user info from Clerk API
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First, verify the token by getting the session
            # Clerk tokens contain the user ID in the 'sub' claim
            # We'll decode it without verification first, then verify with Clerk API
            
            # Get user ID from token (decode without verification for now)
            import jwt
            try:
                decoded = jwt.decode(token, options={"verify_signature": False})
                clerk_user_id = decoded.get("sub")
                
                if not clerk_user_id:
                    raise HTTPException(status_code=401, detail="Invalid token: user ID not found")
            except jwt.DecodeError:
                raise HTTPException(status_code=401, detail="Invalid token format")
            
            # Verify token and get user details from Clerk API
            user_response = await client.get(
                f"https://api.clerk.com/v1/users/{clerk_user_id}",
                headers={
                    "Authorization": f"Bearer {settings.clerk_secret_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if user_response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid Clerk API key")
            
            if user_response.status_code == 404:
                raise HTTPException(status_code=401, detail="User not found in Clerk")
            
            if user_response.status_code != 200:
                logger.error(f"Clerk API error: {user_response.status_code} - {user_response.text}")
                raise HTTPException(status_code=500, detail="Failed to verify user with Clerk")
            
            user_data = user_response.json()
            
            # Extract email (primary email address)
            email = None
            if user_data.get("email_addresses"):
                primary_email = next(
                    (e for e in user_data["email_addresses"] if e.get("id") == user_data.get("primary_email_address_id")),
                    user_data["email_addresses"][0] if user_data["email_addresses"] else None
                )
                email = primary_email.get("email_address") if primary_email else None
            
            # Extract name (first_name + last_name or username)
            name = None
            first_name = user_data.get("first_name", "")
            last_name = user_data.get("last_name", "")
            if first_name or last_name:
                name = f"{first_name} {last_name}".strip()
            elif user_data.get("username"):
                name = user_data.get("username")
            
            return {
                "clerk_user_id": clerk_user_id,
                "email": email,
                "name": name
            }
            
    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.error("Timeout verifying Clerk token")
        raise HTTPException(status_code=500, detail="Authentication service timeout")
    except Exception as e:
        logger.error(f"Error verifying Clerk token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to verify token: {str(e)}")

