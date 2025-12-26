from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.api.routes import router
from app.api.users import router as users_router
from app.api.projects import router as projects_router
from app.api.project_chunks_embeddings import router as project_chunks_embeddings_router
from app.config import settings
from contextlib import asynccontextmanager

# Configure logging from settings
logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: Code that runs when the app starts
    logging.info("=" * 60)
    logging.info(f"🚀 {settings.app_name} starting up...")
    logging.info("=" * 60)
    
    # App Settings
    logging.info("📋 App Configuration:")
    logging.info(f"  Environment: {settings.environment}")
    logging.info(f"  Debug mode: {settings.debug}")
    logging.info(f"  Log level: {settings.log_level}")
    
    # Server Settings
    logging.info("🌐 Server Configuration:")
    logging.info(f"  Host: {settings.host}")
    logging.info(f"  Port: {settings.port}")
    logging.info(f"  CORS Origins: {settings.cors_origins}")
    
    # Database Settings
    logging.info("💾 Database Configuration:")
    logging.info(f"  Supabase URL: {'✓ Configured' if settings.supabase_url else '✗ Not set'}")
    logging.info(f"  Database URL: {'✓ Configured' if settings.database_url else '✗ Not set'}")
    logging.info(f"  Qdrant URL: {'✓ Configured' if settings.qdrant_url else '✗ Not set'}")
    
    # LLM Settings
    logging.info("🤖 LLM Configuration:")
    if settings.environment == "production":
        logging.info(f"  Azure OpenAI API: {'✓ Configured' if settings.azure_openai_key else '✗ Not set'}")
        logging.info(f"  Azure Endpoint: {settings.azure_openai_endpoint if settings.azure_openai_endpoint else '✗ Not set'}")
        logging.info(f"  Azure Deployment: {settings.azure_openai_deployment_gpt_4_1 if settings.azure_openai_deployment_gpt_4_1 else '✗ Not set'}")
        logging.info(f"  Azure Timeout: {settings.azure_openai_timeout}s")
    else:
        logging.info(f"  Groq API: {'✓ Configured' if settings.groq_api_key else '✗ Not set'}")
        logging.info(f"  Groq Model: {settings.groq_model}")
    
    # GitHub Settings
    logging.info("🔧 GitHub Configuration:")
    logging.info(f"  GitHub Token: {'✓ Configured' if settings.github_access_token else '✗ Not set'}")
    


    # Auth Settings
    logging.info("🔐 Authentication Configuration:")
    logging.info(f"  Clerk Secret Key: {'✓ Configured' if settings.clerk_secret_key else '✗ Not set'}")
    logging.info(f"  JWT Secret: {'✓ Configured' if settings.jwt_secret else '✗ Not set'}")
    logging.info(f"  JWT Algorithm: {settings.jwt_algorithm}")
    logging.info(f"  JWT Expiration: {settings.jwt_expiration_minutes} minutes")
    
    logging.info("=" * 60)
    logging.info("✅ Startup complete - Ready to accept requests")
    logging.info("=" * 60)
    
    yield  # App runs here
    
    # Shutdown: Code that runs when the app shuts down
    logging.info("=" * 60)
    logging.info("🛑 App is shutting down...")
    logging.info("=" * 60)

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan
)

# Add CORS middleware - configured from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(project_chunks_embeddings_router, prefix="/api/project_chunks_embeddings")
