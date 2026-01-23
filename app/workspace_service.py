"""
GitGuide Workspaces Service
Minimal FastAPI app for workspace-related routes.
Runs on Compute Engine VM with Docker access for user containers.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.files import router as files_router
from app.api.git import router as git_router
from app.api.preview import router as preview_router
from app.api.terminal import router as terminal_router
from app.api.workspaces import router as workspaces_router
from app.config import settings
from app.core.startup import shutdown_services, startup_services

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown events for the workspace service."""
    logger.info("=" * 60)
    logger.info("🚀 GitGuide Workspaces Service starting up...")
    logger.info(f"   Environment: {settings.environment}")
    logger.info(f"   Host: {settings.host}")
    logger.info(f"   Port: {settings.port}")
    logger.info(f"   CORS Origins: {settings.cors_origins}")
    logger.info("=" * 60)

    # Initialize services (Docker client, etc.)
    try:
        await startup_services()
        logger.info("✅ Services initialized")
    except Exception as e:
        logger.warning(f"⚠️  Service initialization warning: {e}")

    yield

    # Shutdown services
    try:
        await shutdown_services()
    except Exception as e:
        logger.warning(f"⚠️  Service shutdown warning: {e}")

    logger.info("🛑 GitGuide Workspaces Service shutting down...")


app = FastAPI(
    title="GitGuide Workspaces Service",
    description="Service for Docker-based coding workspaces with terminal access",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
# Ensure production frontend domain is always allowed
cors_origins = settings.cors_origins
if isinstance(cors_origins, list):
    # If it's a list, ensure https://gitguide.dev is included
    if "*" not in cors_origins and "https://gitguide.dev" not in cors_origins:
        cors_origins = cors_origins + ["https://gitguide.dev"]
elif cors_origins != "*":
    # If it's a string and not "*", ensure https://gitguide.dev is included
    cors_origins = ["https://gitguide.dev"] + (
        [cors_origins] if isinstance(cors_origins, str) else cors_origins
    )

logger.info(f"CORS Origins configured: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include workspace-related routers
app.include_router(workspaces_router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(files_router, prefix="/api/workspaces", tags=["files"])
app.include_router(terminal_router, prefix="/api/terminal", tags=["terminal"])
app.include_router(preview_router, prefix="/api/preview", tags=["preview"])
app.include_router(git_router, prefix="/api/git", tags=["git"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Check if Docker is available
    try:
        from app.services.docker_client import get_docker_client

        docker_client = get_docker_client()
        docker_available = docker_client.is_docker_available()
    except Exception:
        docker_available = False

    return {
        "status": "healthy" if docker_available else "degraded",
        "service": "workspaces",
        "environment": settings.environment,
        "docker_available": docker_available,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "GitGuide Workspaces Service",
        "version": "1.0.0",
        "docs": "/docs",
    }
