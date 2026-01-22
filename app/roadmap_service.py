"""
GitGuide Roadmap Service
Minimal FastAPI app for roadmap generation.
Deployed separately on Cloud Run with higher resources (2 vCPU, 2Gi RAM).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.roadmap_generation import router as roadmap_gen_router

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

# Include roadmap generation router
app.include_router(roadmap_gen_router, prefix="/api/roadmap", tags=["roadmap-generation"])


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
