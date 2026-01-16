"""
Tests for ChunkStorage
"""

import uuid
from unittest.mock import Mock

import pytest


class TestChunkStorage:
    """Test cases for ChunkStorage"""

    def test_store_chunks_success(self, mock_supabase_client):
        """Test store_chunks - successful storage"""
        from app.services.chunk_storage import store_chunks

        project_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        chunks = [
            {
                "project_id": project_id,
                "file_path": "test.py",
                "chunk_index": 0,
                "language": "python",
                "content": "def hello():",
                "token_count": 5,
            }
        ]

        # Mock Supabase response with proper query chain
        mock_table = mock_supabase_client.table.return_value
        mock_insert_chain = Mock()
        mock_response = Mock()
        mock_response.data = [{"id": chunk_id, **chunks[0]}]
        mock_insert_chain.execute.return_value = mock_response
        mock_table.insert.return_value = mock_insert_chain

        chunk_ids = store_chunks(project_id, chunks)

        assert len(chunk_ids) == 1
        assert chunk_ids[0] == chunk_id
        mock_table.insert.assert_called_once()

    def test_store_chunks_multiple(self, mock_supabase_client):
        """Test store_chunks - multiple chunks"""
        from app.services.chunk_storage import store_chunks

        project_id = str(uuid.uuid4())
        chunk_ids_list = [str(uuid.uuid4()) for _ in range(3)]
        chunks = [
            {
                "project_id": project_id,
                "file_path": "test.py",
                "chunk_index": i,
                "language": "python",
                "content": f"chunk {i}",
                "token_count": 5,
            }
            for i in range(3)
        ]

        # Mock Supabase response
        mock_table = mock_supabase_client.table.return_value
        mock_insert_chain = Mock()
        mock_response = Mock()
        mock_response.data = [{"id": chunk_ids_list[i], **chunks[i]} for i in range(3)]
        mock_insert_chain.execute.return_value = mock_response
        mock_table.insert.return_value = mock_insert_chain

        chunk_ids = store_chunks(project_id, chunks)

        assert len(chunk_ids) == 3

    def test_store_chunks_empty(self, mock_supabase_client):
        """Test store_chunks - empty chunks list"""
        from app.services.chunk_storage import store_chunks

        project_id = str(uuid.uuid4())

        # Mock Supabase response
        mock_table = mock_supabase_client.table.return_value
        mock_insert_chain = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_insert_chain.execute.return_value = mock_response
        mock_table.insert.return_value = mock_insert_chain

        chunk_ids = store_chunks(project_id, [])

        assert len(chunk_ids) == 0

    def test_store_chunks_failure(self, mock_supabase_client):
        """Test store_chunks - Supabase failure"""
        from app.services.chunk_storage import store_chunks

        project_id = str(uuid.uuid4())
        chunks = [
            {
                "project_id": project_id,
                "file_path": "test.py",
                "chunk_index": 0,
                "language": "python",
                "content": "def hello():",
                "token_count": 5,
            }
        ]

        # Mock Supabase failure
        mock_table = mock_supabase_client.table.return_value
        mock_insert_chain = Mock()
        mock_response = Mock()
        mock_response.data = None
        mock_insert_chain.execute.return_value = mock_response
        mock_table.insert.return_value = mock_insert_chain

        with pytest.raises(RuntimeError):
            store_chunks(project_id, chunks)
