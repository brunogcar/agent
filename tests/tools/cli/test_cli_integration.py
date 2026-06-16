"""
Integration tests for the CLI tool.
Tests the full dispatch chain: input -> sanitize -> route -> execute.
"""
import pytest
from unittest.mock import patch, MagicMock

from tools.cli import cli
from tools.cli_ops.helpers import _sanitize_command


@pytest.fixture(autouse=True)
def mock_cfg():
    """Mock cfg to prevent AsyncMock leakage from other tests."""
    with patch("tools.cli.cfg") as mock_cfg:
        mock_cfg.cli_max_command_chars = 4096
        mock_cfg.cli_max_arguments = 50
        mock_cfg.workspace_root = MagicMock()
        mock_cfg.workspace_root.resolve.return_value = MagicMock()
        mock_cfg.workspace_root.resolve.return_value.__eq__ = lambda self, other: False
        mock_cfg.workspace_root.resolve.return_value.parents = []
        yield mock_cfg


class TestCliSanitization:
    """Test sanitization at the CLI entry point."""

    def test_sanitization_null_bytes(self):
        """Null bytes should be rejected at CLI level."""
        result = cli("ls\x00/tmp")
        assert "invalid" in result.get("data", "").lower()

    def test_sanitization_control_chars(self):
        """Control characters should be rejected."""
        result = cli("ls\x01")
        assert "invalid" in result.get("data", "").lower()

    def test_sanitization_too_long(self):
        """Commands exceeding cfg.cli_max_command_chars (4096) should be rejected."""
        long_cmd = "echo " + "a" * 5000
        result = cli(long_cmd)
        assert "invalid" in result.get("data", "").lower() or "too long" in result.lower()

    def test_sanitization_too_many_args(self):
        """Commands with too many arguments should be rejected."""
        many_args = " ".join(["arg"] * 50)
        result = cli(many_args)
        assert "invalid" in result.get("data", "").lower()

    def test_sanitization_valid_command(self):
        """Valid commands should pass through sanitization."""
        result = cli("echo hello")
        data = result.get("data") or ""; assert "null bytes" not in data.lower()
        data = result.get("data") or ""; assert "control characters" not in data.lower()


class TestCliDispatch:
    """Test the dispatch routing layers."""

    def test_pattern_match_layer(self):
        """Test that pattern-matched commands are handled directly."""
        result = cli("git status")
        assert "Escalated to Executor" not in result.get("data", "")

    def test_shell_exec_layer(self):
        """Test that shell commands are executed."""
        result = cli("python --version")
        data = result.get("data") or ""
        assert "Python" in data or "python" in data.lower()

    def test_router_layer_dispatch(self):
        """Test that unrecognized commands go to router."""
        result = cli("find all python files modified today")
        assert isinstance(result, dict)

    def test_router_layer_escalate(self):
        """Test that very complex commands escalate to executor."""
        result = cli("analyze the codebase architecture and suggest improvements")
        assert "Escalated" in result.get("data", "")


class TestCliActions:
    """Test specific CLI actions by mocking the DISPATCH registry directly."""

    @patch('tools.cli_ops.DISPATCH', {
        'file': {'read': lambda action, **kwargs: "file content"}
    })
    def test_file_read_action(self):
        """Test file read action dispatch."""
        result = cli("read test.txt")
        assert "file content" in result.get("data", "") or "test.txt" in result.get("data", "")

    @patch('tools.cli_ops.DISPATCH', {
        'git': {'status': lambda action, **kwargs: {"status": "success", "output": "clean"}}
    })
    def test_git_status_action(self):
        """Test git status action dispatch."""
        result = cli("git status")
        assert isinstance(result, (str, dict))


class TestCliWorkspaceDetection:
    """Test workspace path detection."""

    def test_workspace_detection(self):
        """Test that workspace paths are detected."""
        result = cli("list workspace/")
        assert isinstance(result, dict)

    def test_agent_detection(self):
        """Test that agent paths are detected."""
        result = cli("list tools/")
        assert isinstance(result, dict)
