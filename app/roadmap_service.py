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
    logger.debug(
        f"🔐 Verifying internal auth token (token provided: {x_internal_token is not None})"
    )

    if not settings.internal_auth_token:
        logger.error("❌ INTERNAL_AUTH_TOKEN not configured - internal endpoints disabled")
        raise HTTPException(status_code=503, detail="Internal auth not configured")

    if x_internal_token != settings.internal_auth_token:
        logger.warning(
            f"⚠️  Invalid internal auth token attempt (expected: {settings.internal_auth_token[:10]}..., got: {x_internal_token[:10] if x_internal_token else None}...)"
        )
        raise HTTPException(status_code=403, detail="Invalid internal auth token")

    logger.debug("✅ Internal auth token verified successfully")
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
    logger.info("=" * 70)
    logger.info("🔄 INCREMENTAL GENERATION REQUEST RECEIVED")
    logger.info("=" * 70)
    logger.info(f"   📦 Project ID: {request.project_id}")
    logger.info(
        f"   🕐 Timestamp: {__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()}"
    )
    logger.info("=" * 70)

    try:
        logger.info(f"🔄 Starting incremental generation for project_id={request.project_id}")
        logger.debug(f"   Request payload: {request.model_dump()}")

        # Trigger incremental generation (runs synchronously in background)
        # This will run the LangGraph workflow to generate concepts up to n+2 ahead
        logger.info(
            f"📞 Calling trigger_incremental_generation_sync for project_id={request.project_id}"
        )
        trigger_incremental_generation_sync(request.project_id)
        logger.info(
            f"✅ trigger_incremental_generation_sync completed for project_id={request.project_id}"
        )

        logger.info("=" * 70)
        logger.info("✅ INCREMENTAL GENERATION TRIGGERED SUCCESSFULLY")
        logger.info(f"   📦 Project ID: {request.project_id}")
        logger.info("=" * 70)

        return {
            "success": True,
            "message": "Incremental generation triggered",
            "project_id": request.project_id,
        }
    except Exception as e:
        logger.error("=" * 70)
        logger.error("❌ ERROR TRIGGERING INCREMENTAL GENERATION")
        logger.error(f"   📦 Project ID: {request.project_id}")
        logger.error(f"   ⚠️  Error Type: {type(e).__name__}")
        logger.error(f"   ⚠️  Error Message: {str(e)}")
        logger.error("=" * 70, exc_info=True)
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
    logger.info("=" * 70)
    logger.info("🚀 FULL ROADMAP GENERATION REQUEST RECEIVED")
    logger.info("=" * 70)
    logger.info(f"   📦 Project ID: {request.project_id}")
    logger.info(f"   🔗 GitHub URL: {request.github_url}")
    logger.info(f"   📊 Skill Level: {request.skill_level}")
    logger.info(f"   📅 Target Days: {request.target_days}")
    logger.info(
        f"   🕐 Timestamp: {__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()}"
    )
    logger.info("=" * 70)

    try:
        logger.info(f"🚀 Starting full roadmap generation for project_id={request.project_id}")
        logger.debug(f"   Request payload: {request.model_dump()}")

        # Trigger roadmap generation (runs asynchronously)
        # This will run the complete LangGraph workflow:
        # analyze_repo → plan_curriculum → generate_content → generate_tasks
        import asyncio

        logger.info("📞 Creating async task for run_roadmap_generation")
        logger.info(f"   Project ID: {request.project_id}")
        logger.info(f"   GitHub URL: {request.github_url}")
        logger.info(f"   Skill Level: {request.skill_level}")
        logger.info(f"   Target Days: {request.target_days}")

        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
            logger.info(f"✅ Using existing event loop: {loop}")
        except RuntimeError:
            logger.warning("⚠️  No running event loop found, creating new one")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        task = asyncio.create_task(
            run_roadmap_generation(
                project_id=request.project_id,
                github_url=request.github_url,
                skill_level=request.skill_level,
                target_days=request.target_days,
            )
        )
        logger.info("✅ Async task created successfully")
        logger.info(f"   Task object: {task}")
        logger.info(f"   Task done: {task.done()}")
        logger.info(f"   Task cancelled: {task.cancelled()}")
        logger.info("   ⚠️  Task will run in background - check logs for progress")

        logger.info("=" * 70)
        logger.info("✅ FULL ROADMAP GENERATION TRIGGERED SUCCESSFULLY")
        logger.info(f"   📦 Project ID: {request.project_id}")
        logger.info("   ⚠️  Note: Generation runs asynchronously in background")
        logger.info("=" * 70)

        return {
            "success": True,
            "message": "Roadmap generation started",
            "project_id": request.project_id,
        }
    except Exception as e:
        logger.error("=" * 70)
        logger.error("❌ ERROR TRIGGERING ROADMAP GENERATION")
        logger.error(f"   📦 Project ID: {request.project_id}")
        logger.error(f"   ⚠️  Error Type: {type(e).__name__}")
        logger.error(f"   ⚠️  Error Message: {str(e)}")
        logger.error("=" * 70, exc_info=True)
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
