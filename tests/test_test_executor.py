"""
Tests for Test Executor service.
"""

from unittest.mock import Mock

from app.services.test_executor import TestExecutor


class TestTestExecutorService:
    """Test Test Executor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = TestExecutor()

    def test_execute_test_with_command(self):
        """Test executing test with explicit command."""
        mock_docker = Mock()
        mock_docker.exec_command.return_value = (0, "test output")
        self.executor.docker = mock_docker

        result = self.executor.execute_test(
            container_id="test-container",
            test_command="pytest tests/test_example.py -v",
        )

        assert result["success"]
        assert result["passed"]
        assert result["exit_code"] == 0
        assert "test output" in result["output"]
        mock_docker.exec_command.assert_called_once()

    def test_execute_test_with_file_path_python(self):
        """Test executing test with Python file path."""
        mock_docker = Mock()
        mock_docker.exec_command.return_value = (0, "test passed")
        self.executor.docker = mock_docker

        result = self.executor.execute_test(
            container_id="test-container",
            test_file_path="tests/test_example.py",
        )

        assert result["success"]
        assert result["passed"]
        mock_docker.exec_command.assert_called_once()
        # Should infer pytest command
        call_args = mock_docker.exec_command.call_args[1]
        assert "pytest" in call_args["command"]

    def test_execute_test_with_file_path_javascript(self):
        """Test executing test with JavaScript file path."""
        mock_docker = Mock()
        mock_docker.exec_command.return_value = (0, "test passed")
        self.executor.docker = mock_docker

        result = self.executor.execute_test(
            container_id="test-container",
            test_file_path="tests/test_example.js",
        )

        assert result["success"]
        assert result["passed"]
        mock_docker.exec_command.assert_called_once()
        # Should infer npm test command
        call_args = mock_docker.exec_command.call_args[1]
        assert "npm test" in call_args["command"]

    def test_execute_test_failure(self):
        """Test test execution failure."""
        mock_docker = Mock()
        mock_docker.exec_command.return_value = (1, "test failed: assertion error")
        self.executor.docker = mock_docker

        result = self.executor.execute_test(
            container_id="test-container",
            test_command="pytest tests/test_example.py -v",
        )

        assert result["success"]
        assert not result["passed"]
        assert result["exit_code"] == 1
        assert result["error"] is not None
        assert "exit code 1" in result["error"].lower()

    def test_execute_test_error(self):
        """Test test execution error."""
        mock_docker = Mock()
        mock_docker.exec_command.side_effect = Exception("Container not found")
        self.executor.docker = mock_docker

        result = self.executor.execute_test(
            container_id="test-container",
            test_command="pytest tests/test_example.py -v",
        )

        assert not result["success"]
        assert not result["passed"]
        assert result["exit_code"] == -1
        assert "error" in result

    def test_execute_test_missing_params(self):
        """Test test execution with missing parameters."""
        result = self.executor.execute_test(
            container_id="test-container",
            test_file_path=None,
            test_command=None,
        )

        assert not result["success"]
        assert not result["passed"]
        assert "error" in result
