"""
Application startup initialization.
Call this on app startup to initialize services.
"""

import logging

from app.services.rate_limiter import initialize_rate_limiter

logger = logging.getLogger(__name__)


async def startup_services():
    """
    Initialize all services on application startup.
    Call this from FastAPI startup event.
    """
    logger.info("🚀 Initializing application services...")

    # Initialize rate limiter (will use Redis if available, fallback otherwise)
    try:
        await initialize_rate_limiter()
        logger.info("✅ Startup services initialized")
    except Exception as e:
        logger.warning(f"⚠️  Some services failed to initialize: {e}")
        logger.info("   Application will continue with reduced functionality")


async def shutdown_services():
    """
    Cleanup services on application shutdown.
    Call this from FastAPI shutdown event.
    """
    try:
        logger.info("🛑 Shutting down application services...")
        # Add any cleanup logic here
        logger.info("✅ Services shut down")
    except Exception as e:
        # Ignore cancellation errors during shutdown (normal when stopping with Ctrl+C)
        if "CancelledError" not in str(type(e).__name__):
            logger.warning(f"⚠️  Error during shutdown: {e}")
