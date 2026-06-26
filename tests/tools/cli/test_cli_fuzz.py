"""Fuzz tests for CLI input handling.

Tests malicious inputs, edge cases, and boundary conditions.
"""
from __future__ import annotations

import pytest
from tools.cli_ops.helpers import _sanitize_command
from tools.cli_ops.patterns import _match_pattern


class TestFuzzSanitization:
    """Fuzz tests for _sanitize_command."""

    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "passwd",
        "hacked",
        "root@localhost",
        "/etc/passwd",
        "chmod 777 file",
        "del /f file",
        "format C:",
        "diskpart",
        "rd /s /q dir",
        "rmdir /s dir",
    ])
    def test_dangerous_patterns_blocked(self, mock_cfg, cmd):
        """All dangerous patterns should raise ValueError."""
        with pytest.raises(ValueError):
            _sanitize_command(cmd)

    @pytest.mark.parametrize("cmd", [
        "",
        "   ",
        "git status",
        "echo hello",
        "python --version",
    ])
    def test_safe_commands_allowed(self, mock_cfg, cmd):
        """Safe commands should not raise."""
        result = _sanitize_command(cmd)
        assert isinstance(result, str)

    def test_very_long_command(self, mock_cfg, monkeypatch):
        """Very long command should raise ValueError."""
        monkeypatch.setattr(
            "tools.cli_ops.helpers.cfg.cli_max_command_chars", 100
        )
        with pytest.raises(ValueError, match="too long"):
            _sanitize_command("a" * 101)

    def test_unicode_command(self, mock_cfg):
        """Unicode commands should be handled."""
        result = _sanitize_command("echo hello 世界")
        assert "世界" in result


class TestFuzzPatterns:
    """Fuzz tests for pattern matching."""

    @pytest.mark.parametrize("cmd", [
        "GIT STATUS",
        "Git Status",
        "git STATUS",
    ])
    def test_case_insensitive_patterns(self, mock_cfg, cmd):
        """Patterns should be case-insensitive."""
        result = _match_pattern(cmd)
        assert result is not None
        assert result[0] == "git"
        assert result[1] == "status"

    def test_empty_pattern(self, mock_cfg):
        """Empty string should not match any pattern."""
        result = _match_pattern("")
        assert result is None

    def test_only_whitespace(self, mock_cfg):
        """Whitespace-only should not match."""
        result = _match_pattern("   ")
        assert result is None
