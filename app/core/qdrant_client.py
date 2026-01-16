import logging

from qdrant_client import QdrantClient

from app.config import settings

logger = logging.getLogger(__name__)

_qdrant_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """
    Get or create singleton Qdrant client instance
    """
    global _qdrant_client

    if _qdrant_client is None:
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL is not configured. Please set it in your .env file.")

        try:
            _qdrant_client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
            )
            logger.info("Qdrant client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            raise

    return _qdrant_client
