"""Fuzz tests for cli input sanitization and edge cases."""
import pytest
from unittest.mock import patch, MagicMock
from tools.cli_ops.helpers import _sanitize_command
from tools.cli import cli


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


class TestSanitization:
    """Test the _sanitize_command function directly."""

    def test_null_byte_rejection(self):
        with pytest.raises(ValueError, match="null bytes"):
            _sanitize_command("ls\x00/tmp")

    def test_control_char_rejection(self):
        with pytest.raises(ValueError, match="control characters"):
            _sanitize_command("ls\x01")

    def test_long_command_rejection(self):
        # Generate a command longer than 4096 chars (new limit)
        with pytest.raises(ValueError, match="too long"):
            _sanitize_command("a" * 5000)

    def test_too_many_args_rejection(self):
        with pytest.raises(ValueError, match="too many arguments"):
            _sanitize_command("  ".join(["arg"] * 50))

    def test_whitespace_normalization(self):
        result = _sanitize_command("ls   -la    /tmp")
        assert result == "ls -la /tmp"

    def test_valid_command_passes(self):
        result = _sanitize_command("git status")
        assert result == "git status"

    def test_empty_command_passes(self):
        result = _sanitize_command("")
        assert result == ""

    def test_single_space_passes(self):
        result = _sanitize_command(" ")
        assert result == ""


class TestFuzzInputs:
    """Test with various malicious or edge-case inputs."""

    fuzz_inputs = [
        "; rm -rf /",           # Command injection attempt
        "| cat /etc/passwd",     # Pipe
        "&& echo hacked",        # Chained command
        "$(whoami)",             # Command substitution
        "`whoami`",              # Backtick
        "a" * 1000,              # Long input (but under 4096 limit)
        "\x00\x01\x02",          # Control chars
        "ls /tmp; rm -rf /",     # Multiple commands
        "python -c \"import os; os.system('rm -rf /')\"",  # Python injection
        "echo $(cat /etc/passwd)",  # Command substitution in echo
        "git; rm -rf /",          # Chained git command
        "file < /etc/passwd",     # File redirection
        "file > output.txt",      # File redirection
        "file | grep secret",     # Pipe
        "rm -rf / --no-preserve-root",  # Dangerous rm
        "chmod 777 /etc",         # Dangerous chmod
    ]

    @pytest.mark.parametrize("command", fuzz_inputs)
    def test_fuzz_inputs_no_crash(self, command):
        """Ensure no crashes with malicious input."""
        try:
            result = cli(command)
            # Should return a dict, not crash
            assert isinstance(result, dict)
            # Should not execute dangerous commands
            assert result is not None
            assert result.get("status") is not None
        except Exception as e:
            # Acceptable: validation errors
            assert "Invalid" in str(e) or "Error" in str(e)

    @pytest.mark.parametrize("command", fuzz_inputs)
    def test_fuzz_inputs_safe_output(self, command):
        """Ensure dangerous commands are not executed."""
        result = cli(command)
        # Should not contain evidence of dangerous execution
        dangerous_patterns = [
            "rm -rf",
            "passwd",
            "hacked",
            "root@",
            "etc/passwd",
            "chmod 777",
        ]
        output_text = str(result.get("data", ""))
        for pattern in dangerous_patterns:
            assert pattern not in output_text.lower(),                 f"Dangerous pattern '{pattern}' found in output for command: {command[:50]}"
