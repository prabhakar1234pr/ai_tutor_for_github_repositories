"""
HTTP client for calling the roadmap service from the main API.

This module provides functions to delegate LangGraph workflows to the
dedicated roadmap Cloud Run service, ensuring all agent nodes execute
in the roadmap service container.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _get_identity_token_sync(target_url: str) -> str:
    """
    Get a Google Cloud Identity token for service-to-service authentication.

    Uses the GCP metadata server to fetch an identity token for the target service.
    This is the standard way to get identity tokens in Cloud Run.

    This is a synchronous function that should be called from async context
    using asyncio.to_thread or similar.

    Args:
        target_url: The target Cloud Run service URL

    Returns:
        Identity token as a string
    """
    try:
        # Use httpx for synchronous request to metadata server
        # This is the standard way in GCP/Cloud Run
        metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
        params = {"audience": target_url}
        headers = {"Metadata-Flavor": "Google"}

        # Use httpx.Client for synchronous request
        with httpx.Client(timeout=10.0) as client:
            response = client.get(metadata_url, params=params, headers=headers)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"❌ Failed to get identity token from metadata server: {e}", exc_info=True)
        # If identity token fails, we'll fall back to X-Internal-Token
        raise


async def _get_identity_token(target_url: str) -> str:
    """
    Async wrapper to get Google Cloud Identity token.

    Args:
        target_url: The target Cloud Run service URL

    Returns:
        Identity token as a string
    """
    import asyncio

    return await asyncio.to_thread(_get_identity_token_sync, target_url)


async def call_roadmap_service_incremental(project_id: str) -> dict:
    """
    Call the roadmap service to trigger incremental concept generation.

    This delegates the LangGraph incremental generation workflow to the
    roadmap service, which runs all agent nodes (memory_context, generate_content, etc.)
    in the dedicated Cloud Run container.

    Args:
        project_id: UUID of the project

    Returns:
        dict with success status and message

    Raises:
        httpx.HTTPError: If the HTTP request fails
        ValueError: If roadmap service URL is not configured
    """
    if not settings.roadmap_service_url:
        logger.error("❌ ROADMAP_SERVICE_URL not configured - cannot call roadmap service")
        raise ValueError("Roadmap service URL not configured")

    url = f"{settings.roadmap_service_url}/api/roadmap/incremental-generate"

    # Get Google Cloud Identity token for service-to-service authentication
    try:
        identity_token = await _get_identity_token(settings.roadmap_service_url)
        logger.info("🔐 Got Google Cloud Identity token for service-to-service auth")
    except Exception as e:
        logger.error(f"❌ Failed to get identity token: {e}")
        # Fallback to internal auth token if identity token fails
        if not settings.internal_auth_token:
            raise ValueError(
                "Failed to get identity token and INTERNAL_AUTH_TOKEN not configured"
            ) from e
        logger.warning("⚠️  Falling back to X-Internal-Token header")
        identity_token = None

    headers = {
        "Content-Type": "application/json",
    }

    # Use identity token if available, otherwise fall back to X-Internal-Token
    if identity_token:
        headers["Authorization"] = f"Bearer {identity_token}"
    elif settings.internal_auth_token:
        headers["X-Internal-Token"] = settings.internal_auth_token
    else:
        raise ValueError("No authentication method available")
    payload = {"project_id": project_id}

    logger.info("=" * 70)
    logger.info("📞 CALLING ROADMAP SERVICE FOR INCREMENTAL GENERATION")
    logger.info("=" * 70)
    logger.info(f"   📦 Project ID: {project_id}")
    logger.info(f"   🌐 Service URL: {url}")
    logger.info(
        f"   🕐 Timestamp: {__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()}"
    )
    logger.info("=" * 70)

    try:
        logger.info(f"📡 Making HTTP POST request to: {url}")
        logger.debug(f"   Headers: {dict(headers)}")
        logger.debug(f"   Payload: {payload}")

        async with httpx.AsyncClient(timeout=300.0) as client:
            logger.info("⏳ Waiting for roadmap service response...")
            logger.info(f"📤 Sending request with headers: {dict(headers)}")
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"📥 Received response: Status {response.status_code}")

            # Log response body for debugging 403 errors
            if response.status_code == 403:
                logger.error("=" * 70)
                logger.error("❌ 403 FORBIDDEN - AUTH FAILED")
                logger.error(f"   Request URL: {url}")
                logger.error(f"   Request Headers: {dict(headers)}")
                logger.error(f"   Response Status: {response.status_code}")
                logger.error(f"   Response Body: {response.text}")
                logger.error(
                    f"   Token sent (first 30 chars): {settings.internal_auth_token[:30] if settings.internal_auth_token else 'None'}..."
                )
                logger.error("=" * 70)

            response.raise_for_status()

            result = response.json()
            logger.info("=" * 70)
            logger.info("✅ ROADMAP SERVICE RESPONDED SUCCESSFULLY")
            logger.info(f"   📦 Project ID: {project_id}")
            logger.info(f"   ✅ Message: {result.get('message', 'success')}")
            logger.info("=" * 70)
            return result

    except httpx.HTTPError as e:
        logger.error("=" * 70)
        logger.error("❌ HTTP ERROR CALLING ROADMAP SERVICE (INCREMENTAL)")
        logger.error(f"   📦 Project ID: {project_id}")
        logger.error(f"   🌐 URL: {url}")
        logger.error(f"   ⚠️  Error Type: {type(e).__name__}")
        logger.error(f"   ⚠️  Error Message: {str(e)}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"   📥 Response Status: {e.response.status_code}")
            logger.error(f"   📥 Response Body: {e.response.text[:500]}")
        logger.error("=" * 70, exc_info=True)
        raise
    except Exception as e:
        logger.error("=" * 70)
        logger.error("❌ UNEXPECTED ERROR CALLING ROADMAP SERVICE (INCREMENTAL)")
        logger.error(f"   📦 Project ID: {project_id}")
        logger.error(f"   🌐 URL: {url}")
        logger.error(f"   ⚠️  Error Type: {type(e).__name__}")
        logger.error(f"   ⚠️  Error Message: {str(e)}")
        logger.error("=" * 70, exc_info=True)
        raise


async def call_roadmap_service_generate(
    project_id: str,
    github_url: str,
    skill_level: str,
    target_days: int,
) -> dict:
    """
    Call the roadmap service to trigger full roadmap generation.

    This delegates the complete LangGraph workflow to the roadmap service,
    which runs all agent nodes (analyze_repo, plan_curriculum, generate_content, etc.)
    in the dedicated Cloud Run container.

    Args:
        project_id: UUID of the project
        github_url: GitHub repository URL
        skill_level: beginner/intermediate/advanced
        target_days: Number of days for the roadmap

    Returns:
        dict with success status and message

    Raises:
        httpx.HTTPError: If the HTTP request fails
        ValueError: If roadmap service URL is not configured
    """
    if not settings.roadmap_service_url:
        logger.error("❌ ROADMAP_SERVICE_URL not configured - cannot call roadmap service")
        raise ValueError("Roadmap service URL not configured")

    url = f"{settings.roadmap_service_url}/api/roadmap/generate-internal"

    # Get Google Cloud Identity token for service-to-service authentication
    try:
        identity_token = await _get_identity_token(settings.roadmap_service_url)
        logger.info("🔐 Got Google Cloud Identity token for service-to-service auth")
    except Exception as e:
        logger.error(f"❌ Failed to get identity token: {e}")
        # Fallback to internal auth token if identity token fails
        if not settings.internal_auth_token:
            raise ValueError(
                "Failed to get identity token and INTERNAL_AUTH_TOKEN not configured"
            ) from e
        logger.warning("⚠️  Falling back to X-Internal-Token header")
        identity_token = None

    headers = {
        "Content-Type": "application/json",
    }

    # Use identity token if available, otherwise fall back to X-Internal-Token
    if identity_token:
        headers["Authorization"] = f"Bearer {identity_token}"
    elif settings.internal_auth_token:
        headers["X-Internal-Token"] = settings.internal_auth_token
    else:
        raise ValueError("No authentication method available")
    payload = {
        "project_id": project_id,
        "github_url": github_url,
        "skill_level": skill_level,
        "target_days": target_days,
    }

    logger.info("=" * 70)
    logger.info("📞 CALLING ROADMAP SERVICE FOR FULL GENERATION")
    logger.info("=" * 70)
    logger.info(f"   📦 Project ID: {project_id}")
    logger.info(f"   🔗 GitHub URL: {github_url}")
    logger.info(f"   📊 Skill Level: {skill_level}")
    logger.info(f"   📅 Target Days: {target_days}")
    logger.info(f"   🌐 Service URL: {url}")
    logger.info(
        f"   🕐 Timestamp: {__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()}"
    )
    logger.info("=" * 70)

    try:
        logger.info(f"📡 Making HTTP POST request to: {url}")
        logger.debug(f"   Headers: {dict(headers)}")
        logger.debug(f"   Payload: {payload}")

        async with httpx.AsyncClient(timeout=300.0) as client:
            logger.info("⏳ Waiting for roadmap service response...")
            logger.info(f"📤 Sending request with headers: {dict(headers)}")
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"📥 Received response: Status {response.status_code}")

            # Log response body for debugging 403 errors
            if response.status_code == 403:
                logger.error("=" * 70)
                logger.error("❌ 403 FORBIDDEN - AUTH FAILED")
                logger.error(f"   Request URL: {url}")
                logger.error(f"   Request Headers: {dict(headers)}")
                logger.error(f"   Response Status: {response.status_code}")
                logger.error(f"   Response Body: {response.text}")
                logger.error(
                    f"   Token sent (first 30 chars): {settings.internal_auth_token[:30] if settings.internal_auth_token else 'None'}..."
                )
                logger.error("=" * 70)

            response.raise_for_status()

            result = response.json()
            logger.info("=" * 70)
            logger.info("✅ ROADMAP SERVICE RESPONDED SUCCESSFULLY")
            logger.info(f"   📦 Project ID: {project_id}")
            logger.info(f"   ✅ Message: {result.get('message', 'success')}")
            logger.info(f"   📊 Response: {result}")
            logger.info("=" * 70)
            return result

    except httpx.HTTPError as e:
        logger.error(f"❌ HTTP error calling roadmap service: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error calling roadmap service: {e}", exc_info=True)
        raise


def call_roadmap_service_incremental_sync(project_id: str) -> dict:
    """
    Synchronous wrapper for incremental generation call.

    This is used by FastAPI BackgroundTasks which doesn't support async directly.

    Args:
        project_id: UUID of the project

    Returns:
        dict with success status and message
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(call_roadmap_service_incremental(project_id))
