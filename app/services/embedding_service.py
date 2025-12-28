import logging
import time
from typing import List, TYPE_CHECKING
from app.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Lazy singleton instance
_embedding_service_instance = None


def get_embedding_service() -> 'EmbeddingService':
    """
    Get or create singleton EmbeddingService instance (lazy initialization).
    
    The model is loaded only on first use, then reused for all subsequent requests.
    This saves 3-4 seconds per request after the first one.
    
    Returns:
        EmbeddingService: Singleton instance with loaded model
    """
    global _embedding_service_instance
    
    if _embedding_service_instance is None:
        # Lazy import - only import when actually needed (avoids slow TensorFlow init on startup)
        from sentence_transformers import SentenceTransformer
        
        logger.info(f"🤖 Loading embedding model (first use - this may take a few seconds)...")
        logger.info(f"   Model: {settings.embedding_model_name}")
        model = SentenceTransformer(settings.embedding_model_name)
        _embedding_service_instance = EmbeddingService(model)
        logger.info(f"✅ EmbeddingService ready (will reuse for future requests)")
    
    return _embedding_service_instance


class EmbeddingService:
    def __init__(self, model: 'SentenceTransformer' = None):
        """
        Initialize EmbeddingService with a pre-loaded model.
        
        Args:
            model: Pre-loaded SentenceTransformer model. If None, loads the model (for testing).
        """
        if model is None:
            # Lazy import - only import when actually needed
            from sentence_transformers import SentenceTransformer
            
            # Allow direct instantiation for testing purposes
            logger.info(f"🤖 Initializing EmbeddingService with model: {settings.embedding_model_name}")
            self.model = SentenceTransformer(settings.embedding_model_name)
            logger.info(f"✅ EmbeddingService initialized successfully")
        else:
            # Use provided model (singleton pattern)
            self.model = model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        """
        if not texts:
            logger.warning("⚠️  No texts provided for embedding generation")
            return []
        
        logger.info(f"🧮 Generating embeddings for {len(texts)} texts")
        logger.debug(f"   Model: {settings.embedding_model_name}")
        logger.debug(f"   Batch size: 32")
        logger.debug(f"   Normalize embeddings: True")
        
        start_time = time.time()
        
        # Calculate total text size
        total_chars = sum(len(text) for text in texts)
        logger.debug(f"   Total characters: {total_chars:,}")
        
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        
        duration = time.time() - start_time
        embedding_dim = len(embeddings[0]) if len(embeddings) > 0 else 0
        
        logger.info(f"✅ Generated {len(embeddings)} embeddings (dim={embedding_dim}) in {duration:.2f}s")
        if duration > 0:
            logger.debug(f"   Generation rate: {len(embeddings) / duration:.1f} embeddings/sec")
            logger.debug(f"   Throughput: {total_chars / duration / 1000:.1f}K chars/sec")
        
        return embeddings.tolist()
