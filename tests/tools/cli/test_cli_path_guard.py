"""Tests for path guard integration in CLI.

Verifies that _shell_exec uses core.path_guard for path validation.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from tools.cli_ops.helpers import _shell_exec


class TestShellPathGuard:
    """Verify CLI shell execution uses core.path_guard."""

    def test_shell_uses_path_guard_resolve(self, mock_cfg, monkeypatch):
        """Verify _shell_exec calls resolve_path."""
        calls = []

        def tracking_resolve(path, default_root="agent", require_exists=False):
            calls.append((str(path), default_root))
            resolved = mock_cfg.workspace_root / str(path).lstrip("/\\")
            return resolved, None

        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path", tracking_resolve
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="", returncode=0
            )
            _shell_exec("dir .")

        assert len(calls) > 0

    def test_shell_blocks_outside_agent_root(self, mock_cfg, monkeypatch):
        """Path outside agent_root should be blocked."""
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

    def test_shell_allows_inside_workspace(self, mock_cfg, monkeypatch):
        """Path inside workspace should be allowed."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = mock_cfg.workspace_root / str(path).lstrip("/\\")
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

    def test_mkdir_new_directory(self, mock_cfg, monkeypatch):
        """mkdir for new directory should pass path guard."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = mock_cfg.workspace_root / str(path).lstrip("/\\")
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

    def test_relative_path_traversal_blocked(self, mock_cfg, monkeypatch):
        """Relative path traversal should be blocked."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            resolved = Path("C:/outside.txt")
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
            result = _shell_exec("type ..\\..\\outside.txt")
            assert "outside AGENT_ROOT" in result

    def test_resolve_path_error_handled(self, mock_cfg, monkeypatch):
        """resolve_path returning error should be handled gracefully."""
        def fake_resolve(path, default_root="agent", require_exists=False):
            return None, "Invalid path"

        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path", fake_resolve
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="", returncode=0
            )
            result = _shell_exec("type file.txt")
            # Should skip non-path tokens or handle error gracefully
            assert "error" in result.lower() or result == ""
