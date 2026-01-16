"""
Tests for utility functions
"""

from unittest.mock import AsyncMock, Mock, patch

import jwt
import pytest


class TestClerkAuth:
    """Test cases for clerk_auth utility"""

    @pytest.mark.asyncio
    async def test_verify_clerk_token_success(self):
        """Test verify_clerk_token - successful verification"""
        from app.utils.clerk_auth import verify_clerk_token

        # Mock token
        token = jwt.encode({"sub": "user_123"}, "secret", algorithm="HS256")

        # Mock Clerk API response
        mock_clerk_response = {
            "id": "user_123",
            "email_addresses": [{"id": "email_1", "email_address": "test@example.com"}],
            "primary_email_address_id": "email_1",
            "first_name": "Test",
            "last_name": "User",
        }

        async def mock_get(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_clerk_response
            return mock_response

        with patch("app.utils.clerk_auth.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_class.return_value = mock_client

            with patch("app.config.settings.clerk_secret_key", "test_secret"):
                user_info = await verify_clerk_token(f"Bearer {token}")

        assert user_info["clerk_user_id"] == "user_123"
        assert user_info["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_verify_clerk_token_missing_header(self):
        """Test verify_clerk_token - missing authorization header"""
        from fastapi import HTTPException

        from app.utils.clerk_auth import verify_clerk_token

        with pytest.raises(HTTPException) as exc_info:
            await verify_clerk_token(None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_clerk_token_invalid_format(self):
        """Test verify_clerk_token - invalid header format"""
        from fastapi import HTTPException

        from app.utils.clerk_auth import verify_clerk_token

        with pytest.raises(HTTPException) as exc_info:
            await verify_clerk_token("Invalid token")

        assert exc_info.value.status_code == 401


class TestGitHubUtils:
    """Test cases for github_utils"""

    def test_extract_project_name_success(self):
        """Test extract_project_name - successful extraction"""
        from app.utils.github_utils import extract_project_name

        assert extract_project_name("https://github.com/user/repo") == "repo"
        assert extract_project_name("https://github.com/user/repo.git") == "repo"
        assert extract_project_name("https://github.com/microsoft/vscode") == "vscode"

    def test_extract_project_name_invalid(self):
        """Test extract_project_name - invalid URL"""
        from app.utils.github_utils import extract_project_name

        with pytest.raises(ValueError):
            extract_project_name("invalid-url")

    def test_validate_github_url(self):
        """Test validate_github_url"""
        from app.utils.github_utils import validate_github_url

        # Valid URLs
        assert validate_github_url("https://github.com/user/repo") is True
        assert validate_github_url("http://github.com/user/repo") is True
        assert validate_github_url("https://www.github.com/user/repo") is True

        # Invalid URLs
        assert validate_github_url("invalid-url") is False
        assert validate_github_url("https://gitlab.com/user/repo") is False
        assert validate_github_url("https://github.com/user") is False


class TestTextChunking:
    """Test cases for text_chunking utility"""

    def test_count_tokens(self):
        """Test count_tokens"""
        from app.utils.text_chunking import count_tokens

        # Simple test - token count should be positive
        count = count_tokens("Hello world")
        assert count > 0

    def test_chunk_text_small_file(self):
        """Test chunk_text - small file that fits in one chunk"""
        from app.utils.text_chunking import chunk_text

        content = "def hello():\n    print('Hello')"
        chunks = chunk_text(
            project_id="project_123", file_path="test.py", content=content, language="python"
        )

        assert len(chunks) >= 1
        assert chunks[0]["project_id"] == "project_123"
        assert chunks[0]["file_path"] == "test.py"
        assert chunks[0]["language"] == "python"
        assert "content" in chunks[0]
        assert "token_count" in chunks[0]

    def test_chunk_text_large_file(self):
        """Test chunk_text - large file that needs multiple chunks"""
        from app.utils.text_chunking import chunk_text

        # Create content that will definitely exceed chunk size
        content = "def hello():\n    print('Hello')\n" * 1000
        chunks = chunk_text(
            project_id="project_123", file_path="test.py", content=content, language="python"
        )

        # Should create multiple chunks
        assert len(chunks) > 1
        # Verify all chunks have required fields
        for chunk in chunks:
            assert chunk["project_id"] == "project_123"
            assert chunk["chunk_index"] >= 0
            assert "content" in chunk
            assert "token_count" in chunk

    def test_chunk_files_success(self, mock_github_files):
        """Test chunk_files - successful chunking"""
        from app.utils.text_chunking import chunk_files

        chunks = chunk_files(project_id="project_123", files=mock_github_files)

        assert len(chunks) > 0
        # Verify all chunks have required fields
        for chunk in chunks:
            assert chunk["project_id"] == "project_123"
            assert "file_path" in chunk
            assert "content" in chunk
            assert "language" in chunk
            assert "token_count" in chunk

    def test_chunk_files_empty(self):
        """Test chunk_files - empty files list"""
        from app.utils.text_chunking import chunk_files

        chunks = chunk_files(project_id="project_123", files=[])

        assert len(chunks) == 0
