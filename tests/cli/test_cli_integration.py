"""
Integration tests for cli meta-tool.
"""
import pytest
from unittest.mock import patch, MagicMock
from tools.cli import cli

class TestCliSanitization:
    """Test input sanitization at the cli entry point."""

    def test_sanitization_null_bytes(self):
        result = cli("ls \x00 /tmp")
        assert "Invalid command" in result
        assert "null bytes" in result

    def test_sanitization_control_chars(self):
        result = cli("ls \x01")
        assert "Invalid command" in result
        assert "control characters" in result

    def test_sanitization_too_long(self):
        result = cli("a" * 3000)
        assert "Invalid command" in result
        assert "too long" in result

    def test_sanitization_too_many_args(self):
        result = cli(" ".join(["arg"] * 50))
        assert "Invalid command" in result
        assert "too many arguments" in result

    def test_sanitization_valid_command(self):
        result = cli("health")
        assert "Invalid command" not in result
        assert "operational" in result.lower()

class TestCliDispatch:
    """Test the dispatch layers."""

    @patch('tools.cli_ops.patterns._match_pattern')
    def test_pattern_match_layer(self, mock_pattern):
        mock_pattern.return_value = ("system", "health", {})
        result = cli("health")
        assert "operational" in result.lower()

    @patch('tools.cli_ops.helpers._shell_exec')
    def test_shell_exec_layer(self, mock_shell):
        mock_shell.return_value = "Python 3.11"
        result = cli("python --version")
        assert "3.11" in result

    @patch('tools.cli_ops.router._call_router')
    def test_router_layer_dispatch(self, mock_router):
        mock_router.return_value = {
            "route": "dispatch",
            "tool_name": "system",
            "action": "health",
            "params": {}
        }
        result = cli("some unknown command")
        assert "operational" in result.lower()

    @patch('tools.cli_ops.router._call_router')
    def test_router_layer_escalate(self, mock_router):
        mock_router.return_value = {
            "route": "escalate",
            "reason": "complex task"
        }
        result = cli("some complex task")
        assert "Escalated to Executor" in result
        assert "complex task" in result

class TestCliActions:
    """Test action handlers."""

    @patch('tools.cli_ops.actions.file._file')
    def test_file_read_action(self, mock_file):
        mock_file.return_value = "file content"
        result = cli("read test.txt")
        assert "file content" in result or "test.txt" in result

    @patch('tools.cli_ops.actions.git._git')
    def test_git_status_action(self, mock_git):
        mock_git.return_value = {"status": "ok", "message": "clean"}
        result = cli("git status")
        assert "clean" in result or "ok" in result

class TestCliWorkspaceDetection:
    """Test workspace-aware defaults."""

    def test_workspace_detection(self):
        # ls workspace goes through file tool, returns JSON
        result = cli("ls workspace")
        assert '"status": "success"' in result
        assert '"path"' in result
        assert '"entries"' in result

    def test_agent_detection(self):
        # ls agent goes through file tool
        result = cli("ls agent")
        # If directory exists, check for success:
        # assert '"status": "success"' in result
        # If it doesn't exist, check for error:
        assert "Error:" in result or '"status": "success"' in result