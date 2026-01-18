import logging
import time

import httpx
from supabase import Client, create_client

from app.config import settings

logger = logging.getLogger(__name__)

_supabase_client: Client | None = None


def reset_supabase_client() -> None:
    """Reset the Supabase client instance (useful for connection recovery)."""
    global _supabase_client
    _supabase_client = None
    logger.warning("🔄 Supabase client reset")


def get_supabase_client() -> Client:
    """create and return the Supabase client instance"""
    global _supabase_client

    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise ValueError("Supabase URL or service key is not configured")

        _supabase_client = create_client(settings.supabase_url, settings.supabase_service_key)
        logger.info("Supabase client initialized successfully")

    return _supabase_client


def execute_with_retry(operation, max_retries: int = 3, reset_client_on_error: bool = True):
    """
    Execute a Supabase operation with retry logic for connection errors.

    Args:
        operation: A callable that performs the Supabase operation
        max_retries: Maximum number of retry attempts
        reset_client_on_error: Whether to reset the client on connection errors

    Returns:
        The result of the operation

    Raises:
        The last exception if all retries fail
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return operation()
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException) as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"⚠️  Supabase connection error (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {wait_time}s..."
                )

                # Reset client on connection errors if enabled
                if reset_client_on_error:
                    reset_supabase_client()

                time.sleep(wait_time)
            else:
                logger.error(f"❌ Supabase operation failed after {max_retries + 1} attempts: {e}")
        except Exception:
            # For non-connection errors, don't retry
            raise

    # If we exhausted retries, raise the last exception
    if last_exception:
        raise last_exception
