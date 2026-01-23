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

    logger.info(f"📞 Calling roadmap service for incremental generation: project_id={project_id}")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            logger.info(f"✅ Roadmap service responded: {result.get('message', 'success')}")
            return result

    except httpx.HTTPError as e:
        logger.error(f"❌ HTTP error calling roadmap service: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error calling roadmap service: {e}", exc_info=True)
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

    logger.info(
        f"📞 Calling roadmap service for full generation: "
        f"project_id={project_id}, skill_level={skill_level}, target_days={target_days}"
    )

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            logger.info(f"✅ Roadmap service responded: {result.get('message', 'success')}")
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
