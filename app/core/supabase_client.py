from supabase import create_client, Client
from app.config import settings
import logging


logger = logging.getLogger(__name__)

_supabase_client : Client | None = None

def get_supabase_client() -> Client:
    """create and return the Supabase client instance"""
    global _supabase_client

    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise ValueError("Supabase URL or service key is not configured")

        _supabase_client = create_client(settings.supabase_url, settings.supabase_service_key)
        logger.info("Supabase client initialized successfully")
    
    return _supabase_client


