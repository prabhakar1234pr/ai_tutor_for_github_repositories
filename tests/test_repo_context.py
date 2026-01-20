"""
Tests for Repository Context Builder utility.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agents.utils.repo_context import (
    _detect_test_structure,
    build_notebook_repo_context_for_task_generation,
)


class TestRepoContext:
    """Test Repository Context Builder functionality."""

    def test_detect_test_structure_pytest(self):
        """Test pytest detection."""
        repo_files = [
            {"path": "pytest.ini", "content": "[pytest]"},
            {"path": "tests/test_example.py", "content": "import pytest"},
        ]

        result = _detect_test_structure(repo_files)

        assert result["framework"] == "pytest"
        assert result["has_test_setup"]
        assert "pytest" in result["test_command"]
        assert "tests/" in result["test_directories"]

    def test_detect_test_structure_jest(self):
        """Test Jest detection."""
        repo_files = [
            {
                "path": "package.json",
                "content": '{"scripts": {"test": "jest"}, "dependencies": {"jest": "^29.0.0"}}',
            },
            {"path": "__tests__/test.js", "content": "test('example', () => {});"},
        ]

        result = _detect_test_structure(repo_files)

        assert result["framework"] == "jest"
        assert result["has_test_setup"]
        assert "jest" in result["test_dependencies"]

    def test_detect_test_structure_none(self):
        """Test detection when no test framework found."""
        repo_files = [
            {"path": "main.py", "content": "print('hello')"},
        ]

        result = _detect_test_structure(repo_files)

        assert result["framework"] == "none"
        assert not result["has_test_setup"]

    @pytest.mark.asyncio
    async def test_build_notebook_repo_context_success(self):
        """Test successful notebook repo context building."""
        mock_repo_data = {
            "default_branch": "main",
        }

        mock_tree_data = {
            "tree": [
                {"type": "blob", "path": "package.json", "sha": "sha1"},
                {"type": "blob", "path": "README.md", "sha": "sha2"},
            ]
        }

        mock_blob_data = {
            "encoding": "base64",
            "content": "eyJuYW1lIjogInRlc3QifQ==",  # base64 for {"name": "test"}
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_repo_resp = Mock()
            mock_repo_resp.json.return_value = mock_repo_data
            mock_repo_resp.raise_for_status = Mock()

            mock_tree_resp = Mock()
            mock_tree_resp.json.return_value = mock_tree_data
            mock_tree_resp.raise_for_status = Mock()

            mock_blob_resp = Mock()
            mock_blob_resp.json.return_value = mock_blob_data
            mock_blob_resp.raise_for_status = Mock()

            mock_client.get = AsyncMock(
                side_effect=[mock_repo_resp, mock_tree_resp, mock_blob_resp]
            )

            result = await build_notebook_repo_context_for_task_generation(
                project_id="test-project",
                concept_metadata={},
                user_repo_url="https://github.com/user/repo",
                github_token="test_token",
            )

            assert "repo_structure" in result
            assert "repo_code_context" in result
            assert "existing_test_structure" in result

    @pytest.mark.asyncio
    async def test_build_notebook_repo_context_not_found(self):
        """Test notebook repo context when repo not found."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_resp = Mock()
            mock_resp.status_code = 404
            mock_resp.raise_for_status.side_effect = Exception("404")

            mock_client.get = AsyncMock(side_effect=Exception("404 Not Found"))

            result = await build_notebook_repo_context_for_task_generation(
                project_id="test-project",
                concept_metadata={},
                user_repo_url="https://github.com/user/nonexistent",
            )

            # Should return minimal context
            assert "repo_structure" in result
            assert "existing_test_structure" in result
