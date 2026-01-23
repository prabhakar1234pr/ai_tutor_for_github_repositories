"""
GitGuide Roadmap Service
Minimal FastAPI app for roadmap generation.
Deployed separately on Cloud Run with higher resources (2 vCPU, 2Gi RAM).

All LangGraph workflows execute here:
- Initial roadmap generation (full pipeline)
- Incremental concept generation (lazy loading)
- All agent nodes (analyze_repo, plan_curriculum, generate_content, generate_tasks, etc.)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.services.roadmap_generation import (
    router as roadmap_gen_router,
)
from app.services.roadmap_generation import (
    run_roadmap_generation,
    trigger_incremental_generation_sync,
)

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown events for the roadmap service."""
    logger.info("=" * 60)
    logger.info("🚀 GitGuide Roadmap Service starting up...")
    logger.info(f"   Environment: {settings.environment}")
    logger.info(f"   GCP Project: {settings.gcp_project_id}")
    logger.info(f"   Gemini Model: {settings.gemini_model}")
    logger.info("=" * 60)

    yield

    logger.info("🛑 GitGuide Roadmap Service shutting down...")


app = FastAPI(
    title="GitGuide Roadmap Service",
    description="Dedicated service for LLM-heavy roadmap generation",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include roadmap generation router (public endpoint for initial generation)
app.include_router(roadmap_gen_router, prefix="/api/roadmap", tags=["roadmap-generation"])


# Internal auth dependency for service-to-service calls
async def verify_internal_auth(x_internal_token: str | None = Header(None)):
    """Verify internal auth token for service-to-service calls."""
    if not settings.internal_auth_token:
        logger.warning("⚠️  INTERNAL_AUTH_TOKEN not configured - internal endpoints disabled")
        raise HTTPException(status_code=503, detail="Internal auth not configured")

    if x_internal_token != settings.internal_auth_token:
        logger.warning("⚠️  Invalid internal auth token attempt")
        raise HTTPException(status_code=403, detail="Invalid internal auth token")

    return True


# Internal endpoints for LangGraph workflows
class IncrementalGenerateRequest(BaseModel):
    """Request to trigger incremental concept generation."""

    project_id: str


class GenerateRoadmapInternalRequest(BaseModel):
    """Internal request to trigger full roadmap generation."""

    project_id: str
    github_url: str
    skill_level: str
    target_days: int


@app.post("/api/roadmap/incremental-generate", dependencies=[Depends(verify_internal_auth)])
async def incremental_generate(request: IncrementalGenerateRequest):
    """
    Internal endpoint to trigger incremental concept generation.

    This endpoint is called by the main API service when a user completes
    a concept and needs more concepts generated ahead of their position.

    Requires internal auth token in X-Internal-Token header.
    """
    try:
        logger.info(f"🔄 Incremental generation requested for project_id={request.project_id}")

        # Trigger incremental generation (runs synchronously in background)
        # This will run the LangGraph workflow to generate concepts up to n+2 ahead
        trigger_incremental_generation_sync(request.project_id)

        logger.info(f"✅ Incremental generation triggered for project_id={request.project_id}")

        return {
            "success": True,
            "message": "Incremental generation triggered",
            "project_id": request.project_id,
        }
    except Exception as e:
        logger.error(f"❌ Error triggering incremental generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger incremental generation: {str(e)}"
        ) from e


@app.post("/api/roadmap/generate-internal", dependencies=[Depends(verify_internal_auth)])
async def generate_roadmap_internal(request: GenerateRoadmapInternalRequest):
    """
    Internal endpoint to trigger full roadmap generation.

    This endpoint is called by the main API service (e.g., from embedding pipeline)
    to trigger the complete LangGraph workflow for initial roadmap generation.

    Requires internal auth token in X-Internal-Token header.
    """
    try:
        logger.info(
            f"🚀 Full roadmap generation requested for project_id={request.project_id}, "
            f"skill_level={request.skill_level}, target_days={request.target_days}"
        )

        # Trigger roadmap generation (runs asynchronously)
        # This will run the complete LangGraph workflow:
        # analyze_repo → plan_curriculum → generate_content → generate_tasks
        import asyncio

        asyncio.create_task(
            run_roadmap_generation(
                project_id=request.project_id,
                github_url=request.github_url,
                skill_level=request.skill_level,
                target_days=request.target_days,
            )
        )

        logger.info(f"✅ Full roadmap generation triggered for project_id={request.project_id}")

        return {
            "success": True,
            "message": "Roadmap generation started",
            "project_id": request.project_id,
        }
    except Exception as e:
        logger.error(f"❌ Error triggering roadmap generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger roadmap generation: {str(e)}"
        ) from e


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {
        "status": "healthy",
        "service": "roadmap",
        "environment": settings.environment,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "GitGuide Roadmap Service",
        "version": "1.0.0",
        "docs": "/docs",
    }
