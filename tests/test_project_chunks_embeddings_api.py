"""
Tests for Project Chunks Embeddings API
"""
import pytest
from unittest.mock import Mock, patch
from uuid import uuid4


class TestProjectChunksEmbeddingsAPI:
    """Test cases for /api/project_chunks_embeddings endpoints"""
    
    def test_start_embedding_pipeline_success(self, client, mock_supabase_client):
        """Test POST /api/project_chunks_embeddings/projects/chunks-embeddings/run - successful start"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.eq.return_value.execute.return_value.data = [{
            "project_id": str(project_id),
            "github_url": "https://github.com/user/test-repo",
            "status": "created"
        }]
        
        with patch("app.api.project_chunks_embeddings.run_embedding_pipeline"):
            response = client.post(
                "/api/project_chunks_embeddings/projects/chunks-embeddings/run",
                json={
                    "project_id": str(project_id),
                    "github_url": "https://github.com/user/test-repo"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["project_id"] == str(project_id)
    
    def test_start_embedding_pipeline_project_not_found(self, client, mock_supabase_client):
        """Test POST /api/project_chunks_embeddings/projects/chunks-embeddings/run - project not found"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.eq.return_value.execute.return_value.data = []
        
        response = client.post(
            "/api/project_chunks_embeddings/projects/chunks-embeddings/run",
            json={
                "project_id": str(project_id),
                "github_url": "https://github.com/user/test-repo"
            }
        )
        
        assert response.status_code == 404
    
    def test_start_embedding_pipeline_url_mismatch(self, client, mock_supabase_client):
        """Test POST /api/project_chunks_embeddings/projects/chunks-embeddings/run - URL mismatch"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.eq.return_value.execute.return_value.data = [{
            "project_id": str(project_id),
            "github_url": "https://github.com/user/different-repo",
            "status": "created"
        }]
        
        response = client.post(
            "/api/project_chunks_embeddings/projects/chunks-embeddings/run",
            json={
                "project_id": str(project_id),
                "github_url": "https://github.com/user/test-repo"
            }
        )
        
        assert response.status_code == 400
    
    def test_start_embedding_pipeline_already_processing(self, client, mock_supabase_client):
        """Test POST /api/project_chunks_embeddings/projects/chunks-embeddings/run - already processing"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.eq.return_value.execute.return_value.data = [{
            "project_id": str(project_id),
            "github_url": "https://github.com/user/test-repo",
            "status": "processing"
        }]
        
        response = client.post(
            "/api/project_chunks_embeddings/projects/chunks-embeddings/run",
            json={
                "project_id": str(project_id),
                "github_url": "https://github.com/user/test-repo"
            }
        )
        
        assert response.status_code == 409
    
    def test_get_embedding_status_success(self, client, mock_supabase_client):
        """Test GET /api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/status"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.eq.return_value.execute.return_value.data = [{
            "project_id": str(project_id),
            "status": "ready",
            "error_reason": None,
            "updated_at": "2024-01-01T00:00:00Z"
        }]
        
        response = client.get(
            f"/api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/status"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == str(project_id)
        assert data["status"] == "ready"
    
    def test_get_embedding_status_not_found(self, client, mock_supabase_client):
        """Test GET /api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/status - not found"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.eq.return_value.execute.return_value.data = []
        
        response = client.get(
            f"/api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/status"
        )
        
        assert response.status_code == 404
    
    def test_list_project_chunks_success(self, client, mock_supabase_client):
        """Test GET /api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/chunks"""
        import uuid
        project_id = uuid4()
        chunk_id = str(uuid.uuid4())
        
        # Setup mocks with proper query chains
        mock_table = mock_supabase_client.table.return_value
        
        # Mock: project exists (first select)
        mock_select_chain1 = Mock()
        mock_select_chain1.select.return_value = mock_select_chain1
        mock_select_chain1.eq.return_value = mock_select_chain1
        mock_select_chain1.execute.return_value.data = [{"project_id": str(project_id)}]
        
        # Mock: chunks list (second select with chained methods)
        mock_select_chain2 = Mock()
        mock_select_chain2.select.return_value = mock_select_chain2
        mock_select_chain2.eq.return_value = mock_select_chain2
        mock_select_chain2.order.return_value = mock_select_chain2
        mock_select_chain2.range.return_value = mock_select_chain2
        mock_select_chain2.execute.return_value.data = [
            {
                "id": chunk_id,
                "file_path": "test.py",
                "chunk_index": 0,
                "language": "python",
                "content": "def hello():",
                "token_count": 5,
                "created_at": "2024-01-01T00:00:00Z"
            }
        ]
        
        # Handle multiple table calls
        call_count = [0]
        def table_side_effect(table_name):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call - Projects table
                mock_table1 = Mock()
                mock_table1.select.return_value = mock_select_chain1
                return mock_table1
            else:
                # Second call - project_chunks table
                mock_table2 = Mock()
                mock_table2.select.return_value = mock_select_chain2
                return mock_table2
        
        mock_supabase_client.table.side_effect = table_side_effect
        
        try:
            response = client.get(
                f"/api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/chunks"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == str(project_id)
            assert "chunks" in data
            assert data["count"] == 1
        finally:
            mock_supabase_client.table.side_effect = None
    
    def test_list_project_chunks_with_pagination(self, client, mock_supabase_client):
        """Test GET /api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/chunks with pagination"""
        project_id = uuid4()
        
        # Setup mocks
        mock_table = mock_supabase_client.table.return_value
        
        # Mock: project exists
        mock_select_chain1 = Mock()
        mock_select_chain1.select.return_value = mock_select_chain1
        mock_select_chain1.eq.return_value = mock_select_chain1
        mock_select_chain1.execute.return_value.data = [{"project_id": str(project_id)}]
        
        # Mock: chunks list (empty)
        mock_select_chain2 = Mock()
        mock_select_chain2.select.return_value = mock_select_chain2
        mock_select_chain2.eq.return_value = mock_select_chain2
        mock_select_chain2.order.return_value = mock_select_chain2
        mock_select_chain2.range.return_value = mock_select_chain2
        mock_select_chain2.execute.return_value.data = []
        
        call_count = [0]
        def table_side_effect(table_name):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_table1 = Mock()
                mock_table1.select.return_value = mock_select_chain1
                return mock_table1
            else:
                mock_table2 = Mock()
                mock_table2.select.return_value = mock_select_chain2
                return mock_table2
        
        mock_supabase_client.table.side_effect = table_side_effect
        
        try:
            response = client.get(
                f"/api/project_chunks_embeddings/projects/chunks-embeddings/{project_id}/chunks",
                params={"limit": 50, "offset": 0}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == str(project_id)
            assert data["count"] == 0
        finally:
            mock_supabase_client.table.side_effect = None

