"""Tests for CLI shell execution (Layer 2).

Covers whitelist, flag blocking, path validation, and output formatting.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from tools.cli_ops.helpers import _shell_exec, ALLOWED_COMMANDS, BLOCKED_FLAGS


class TestShellWhitelist:
    """Tests for ALLOWED_COMMANDS whitelist."""

    def test_allowed_command_executes(self, mock_cfg):
        """Whitelisted command should execute."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="hello\n", stderr="", returncode=0
            )
            result = _shell_exec("echo hello")
            assert "hello" in result
            mock_run.assert_called_once()

    def test_blocked_command_rejected(self, mock_cfg):
        """Non-whitelisted command should be rejected."""
        result = _shell_exec("hacktool arg")
        assert "not in the allowlist" in result

    def test_blocked_flag_rejected(self, mock_cfg):
        """Dangerous flags should be blocked."""
        result = _shell_exec("python -c 'import os'")
        assert "blocked for security" in result

    def test_shell_operator_rejected(self, mock_cfg):
        """Shell operators should be rejected."""
        result = _shell_exec("echo hello | cat")
        assert "not allowed" in result


class TestShellPathGuard:
    """Tests for path guard integration in shell execution."""

    def test_path_outside_agent_root_blocked(self, mock_cfg, monkeypatch):
        """Paths outside agent_root should be blocked."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = Path("C:/Windows/System32/drivers/etc/hosts")
            return resolved, None

        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path", fake_resolve
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: False
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="", returncode=0
            )
            result = _shell_exec("type hosts")
            assert "outside AGENT_ROOT" in result

    def test_path_inside_workspace_allowed(self, mock_cfg, monkeypatch):
        """Paths inside workspace should be allowed."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = mock_cfg.workspace_root / "file.txt"
            return resolved, None

        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path", fake_resolve
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="file content\n", stderr="", returncode=0
            )
            result = _shell_exec("type file.txt")
            assert "outside" not in result.lower()
            assert "file content" in result

    def test_mkdir_inside_allowed(self, mock_cfg, monkeypatch):
        """mkdir inside workspace should work."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = mock_cfg.workspace_root / "newdir"
            return resolved, None

        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path", fake_resolve
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="", returncode=0
            )
            result = _shell_exec("mkdir newdir")
            assert "outside" not in result.lower()

    def test_nonexistent_path_allowed(self, mock_cfg, monkeypatch):
        """Non-existent paths should be validated by resolve_path, not rejected."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = mock_cfg.workspace_root / "newdir"
            return resolved, None

        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path", fake_resolve
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="", returncode=0
            )
            result = _shell_exec("mkdir newdir")
            assert "outside" not in result.lower()


class TestShellOutput:
    """Tests for shell output handling."""

    def test_stdout_returned(self, mock_cfg):
        """stdout should be returned."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="output\n", stderr="", returncode=0
            )
            result = _shell_exec("echo output")
            assert result == "output"

    def test_stderr_fallback(self, mock_cfg):
        """stderr should be returned if stdout is empty."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="error msg\n", returncode=1
            )
            result = _shell_exec("echo")
            assert "error msg" in result

    def test_timeout_error(self, mock_cfg):
        """Timeout should return error message."""
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            result = _shell_exec("echo test")
            assert "timed out" in result
