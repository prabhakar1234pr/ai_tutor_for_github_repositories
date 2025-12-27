"""
Tests for EmbeddingService
"""
import pytest
from unittest.mock import Mock, patch
import numpy as np


class TestEmbeddingService:
    """Test cases for EmbeddingService"""
    
    @patch("app.services.embedding_service.SentenceTransformer")
    def test_embed_texts_success(self, mock_transformer_class):
        """Test embed_texts - successful embedding generation"""
        from app.services.embedding_service import EmbeddingService
        
        # Mock SentenceTransformer
        mock_model = Mock()
        mock_embeddings = np.array([[0.1] * 384, [0.2] * 384])
        mock_model.encode.return_value = mock_embeddings
        mock_transformer_class.return_value = mock_model
        
        service = EmbeddingService()
        texts = ["Hello world", "Test text"]
        embeddings = service.embed_texts(texts)
        
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 384
        mock_model.encode.assert_called_once()
    
    @patch("app.services.embedding_service.SentenceTransformer")
    def test_embed_texts_empty(self, mock_transformer_class):
        """Test embed_texts - empty input"""
        from app.services.embedding_service import EmbeddingService
        
        mock_model = Mock()
        mock_transformer_class.return_value = mock_model
        
        service = EmbeddingService()
        embeddings = service.embed_texts([])
        
        assert embeddings == []
        mock_model.encode.assert_not_called()
    
    @patch("app.services.embedding_service.SentenceTransformer")
    def test_embed_texts_batch_processing(self, mock_transformer_class):
        """Test embed_texts - batch processing"""
        from app.services.embedding_service import EmbeddingService
        
        mock_model = Mock()
        mock_embeddings = np.array([[0.1] * 384] * 50)
        mock_model.encode.return_value = mock_embeddings
        mock_transformer_class.return_value = mock_model
        
        service = EmbeddingService()
        texts = ["Text"] * 50
        embeddings = service.embed_texts(texts)
        
        assert len(embeddings) == 50
        # Verify batch_size was used
        call_args = mock_model.encode.call_args
        assert call_args[1]["batch_size"] == 32

