from pydantic_settings import BaseSettings
from typing import Optional, Union
from functools import lru_cache
from pathlib import Path
from pydantic import field_validator

# Get the project root directory (one level up from app/)
PROJECT_ROOT = Path(__file__).parent.parent

# Export these for app-wide use
__all__ = ["Settings", "settings", "get_settings"]

class Settings(BaseSettings):
    # App Settings
    app_name: str = "AI Tutor for GitHub Repositories"
    debug: Union[bool, str] = True
    
    @field_validator('debug', mode='before')
    @classmethod
    def parse_debug(cls, v):
        """Parse debug from various formats"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower in ('true', '1', 'yes', 'on'):
                return True
            if v_lower in ('false', '0', 'no', 'off'):
                return False
            # If it's something else (like 'WARN'), default to True for development
            return True
        return bool(v)
    
    # Server Settings
    host: str = "127.0.0.1"
    port: int = 8000
    
    # CORS Settings - Allowed frontend URLs
    cors_origins: Union[str, list[str]] = ["*"]
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list"""
        if isinstance(v, str):
            # Handle comma-separated string from .env
            if v.strip() == "*":
                return ["*"]
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v
    
    # Database Settings - Supabase connection string
    database_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_key: Optional[str] = None
    supabase_url: Optional[str] = None
    
    # PostgreSQL individual connection parameters
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_host: Optional[str] = None
    db_port: Optional[str] = None
    db_name: Optional[str] = None
    
    # Vector Database Settings - Qdrant connection
    qdrant_url: Optional[str] = None
    qdrant_api_key: Optional[str] = None
    
    # Environment (development or production)
    environment: str = "development"
    
    # LLM API Keys - Azure OpenAI (Production)
    azure_openai_key: Optional[str] = None  # Maps to AZURE_OPENAI_KEY
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment_gpt_4_1: Optional[str] = None  # Maps to AZURE_OPENAI_DEPLOYMENT_GPT_4_1
    azure_openai_api_version: str = "2024-02-15-preview"
    azure_openai_timeout: int = 180  # Timeout in seconds
    
    # Authentication
    clerk_secret_key: Optional[str] = None  # Add this line
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60   # For JWT token expiration


    # LLM API Keys - Groq (Development)
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-70b-versatile"
    
    # GitHub API
    github_access_token: Optional[str] = None  # Maps to GITHUB_ACCESS_TOKEN
    
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        # Look for .env in project root (ai_tutor_for_github_repositories/)
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env that aren't defined

@lru_cache()
def get_settings() -> Settings:
    """
    Create and cache a single Settings instance (Singleton pattern).
    Returns the same instance on subsequent calls.
    """
    return Settings()

# Create a global settings instance for convenience
settings = get_settings()

