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

    if not settings.internal_auth_token:
        logger.error("❌ INTERNAL_AUTH_TOKEN not configured - cannot call roadmap service")
        raise ValueError("Internal auth token not configured")

    url = f"{settings.roadmap_service_url}/api/roadmap/incremental-generate"
    headers = {
        "X-Internal-Token": settings.internal_auth_token,
        "Content-Type": "application/json",
    }
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
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"📥 Received response: Status {response.status_code}")

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

    if not settings.internal_auth_token:
        logger.error("❌ INTERNAL_AUTH_TOKEN not configured - cannot call roadmap service")
        raise ValueError("Internal auth token not configured")

    url = f"{settings.roadmap_service_url}/api/roadmap/generate-internal"
    headers = {
        "X-Internal-Token": settings.internal_auth_token,
        "Content-Type": "application/json",
    }
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
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"📥 Received response: Status {response.status_code}")

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
