"""Tests for CLI input sanitization (_sanitize_command)."""
from __future__ import annotations

import pytest
from tools.cli_ops.helpers import _sanitize_command


class TestSanitizeCommand:
    """Unit tests for _sanitize_command."""

    def test_empty_string(self, mock_cfg):
        """Empty string should return empty string."""
        assert _sanitize_command("") == ""

    def test_whitespace_normalization(self, mock_cfg):
        """Multiple spaces should be collapsed."""
        assert _sanitize_command("git   status") == "git status"

    def test_null_bytes_rejected(self, mock_cfg):
        """Null bytes should raise ValueError."""
        with pytest.raises(ValueError, match="null bytes"):
            _sanitize_command("hello\x00world")

    def test_control_characters_rejected(self, mock_cfg):
        """Control characters should raise ValueError."""
        with pytest.raises(ValueError, match="control characters"):
            _sanitize_command("hello\x01world")

    def test_dangerous_patterns_rejected(self, mock_cfg):
        """Dangerous patterns should raise ValueError."""
        with pytest.raises(ValueError, match="blocked pattern"):
            _sanitize_command("rm -rf /")

    def test_too_long_rejected(self, mock_cfg, monkeypatch):
        """Commands exceeding max length should raise ValueError."""
        monkeypatch.setattr(
            "tools.cli_ops.helpers.cfg.cli_max_command_chars", 10
        )
        with pytest.raises(ValueError, match="too long"):
            _sanitize_command("a" * 11)

    def test_too_many_args_rejected(self, mock_cfg, monkeypatch):
        """Commands with too many args should raise ValueError."""
        monkeypatch.setattr(
            "tools.cli_ops.helpers.cfg.cli_max_arguments", 3
        )
        with pytest.raises(ValueError, match="too many arguments"):
            _sanitize_command("a b c d")

    def test_non_string_rejected(self, mock_cfg):
        """Non-string input should raise ValueError."""
        with pytest.raises(ValueError, match="must be a string"):
            _sanitize_command(123)
