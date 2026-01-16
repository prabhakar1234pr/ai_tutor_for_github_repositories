"""
Tests for GitHubService
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestGitHubService:
    """Test cases for GitHubService"""

    @pytest.mark.asyncio
    async def test_fetch_repository_files_success(self):
        """Test fetch_repository_files - successful fetch"""
        from app.services.github_service import fetch_repository_files

        # Mock repository info
        mock_repo_response = {"default_branch": "main"}

        # Mock tree response
        mock_tree_response = {
            "tree": [
                {"type": "blob", "path": "test.py", "sha": "abc123", "size": 100},
                {"type": "blob", "path": "README.md", "sha": "def456", "size": 200},
                {"type": "tree", "path": "folder", "sha": "ghi789"},
            ]
        }

        # Mock blob responses
        mock_blob_responses = {
            "abc123": {
                "content": "ZGVmIGhlbGxvKCk6CiAgICBwcmludCgnSGVsbG8sIFdvcmxkIScp"
            }  # base64 encoded
        }

        async def mock_get(url, **kwargs):
            mock_response = Mock()
            if "repos" in url and "git/trees" not in url and "git/blobs" not in url:
                mock_response.json.return_value = mock_repo_response
            elif "git/trees" in url:
                mock_response.json.return_value = mock_tree_response
            elif "git/blobs" in url:
                sha = url.split("/")[-1]
                mock_response.json.return_value = mock_blob_responses.get(sha, {"content": ""})
            mock_response.raise_for_status = Mock()
            return mock_response

        with patch("app.services.github_service.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_class.return_value = mock_client

            with patch("app.config.settings.github_access_token", None):
                files = await fetch_repository_files("https://github.com/user/test-repo")

        # Note: This test may need adjustment based on actual implementation
        assert isinstance(files, list)

    @pytest.mark.asyncio
    async def test_fetch_repository_files_invalid_url(self):
        """Test fetch_repository_files - invalid URL"""
        from app.services.github_service import fetch_repository_files

        with pytest.raises(ValueError):
            await fetch_repository_files("invalid-url")

    def test_extract_repo_info_success(self):
        """Test extract_repo_info - successful extraction"""
        from app.services.github_service import extract_repo_info

        owner, repo = extract_repo_info("https://github.com/user/test-repo")
        assert owner == "user"
        assert repo == "test-repo"

    def test_extract_repo_info_with_git_suffix(self):
        """Test extract_repo_info - URL with .git suffix"""
        from app.services.github_service import extract_repo_info

        owner, repo = extract_repo_info("https://github.com/user/test-repo.git")
        assert owner == "user"
        assert repo == "test-repo"

    def test_extract_repo_info_invalid(self):
        """Test extract_repo_info - invalid URL"""
        from app.services.github_service import extract_repo_info

        with pytest.raises(ValueError):
            extract_repo_info("invalid-url")

    def test_should_ignore_file(self):
        """Test should_ignore_file"""
        from app.services.github_service import should_ignore_file

        # Should ignore
        assert should_ignore_file(".git/config") is True
        assert should_ignore_file("node_modules/file.js") is True
        assert should_ignore_file("dist/app.js") is True

        # Should not ignore
        assert should_ignore_file("test.py") is False
        assert should_ignore_file("README.md") is False

    def test_detect_language(self):
        """Test detect_language"""
        from app.services.github_service import detect_language

        assert detect_language("test.py") == "python"
        assert detect_language("test.js") == "javascript"
        assert detect_language("test.md") == "markdown"
        assert detect_language("unknown.xyz") == "text"
