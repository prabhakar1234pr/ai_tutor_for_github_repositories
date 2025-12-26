import logging
import time
from typing import List
from sentence_transformers import SentenceTransformer
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        logger.info(f"🤖 Initializing EmbeddingService with model: {settings.embedding_model_name}")
        self.model = SentenceTransformer(settings.embedding_model_name)
        logger.info(f"✅ EmbeddingService initialized successfully")

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
        logger.debug(f"   Generation rate: {len(embeddings) / duration:.1f} embeddings/sec")
        logger.debug(f"   Throughput: {total_chars / duration / 1000:.1f}K chars/sec")
        
        return embeddings.tolist()
