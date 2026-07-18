"""Tests for CLI shell execution (Layer 2).

Covers whitelist, flag blocking, path validation, output formatting,
and Windows command mapping.
"""
from __future__ import annotations

import os
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


class TestShellWindowsCommands:
    """Tests for Windows-specific shell commands (P1 #5).

    The first 5 tests are skipped on non-Windows platforms because the
    actual binaries (dir, type, copy, move, del) only exist on Windows.
    The 6th test runs on Linux but mocks os.name='nt' to verify the
    Windows command mapping logic.
    """

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only command (dir)")
    def test_shell_exec_dir_command(self, mock_cfg, monkeypatch):
        """'dir' (Windows ls) should execute on Windows."""
        # Bypass path validation — 'dir' with no args has no path tokens.
        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path",
            lambda path, default_root="agent", require_exists=False: (Path("."), None)
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="file.txt\nfile2.txt\n", stderr="", returncode=0
            )
            result = _shell_exec("dir")
            assert "file.txt" in result
            mock_run.assert_called_once()

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only command (type)")
    def test_shell_exec_type_command(self, mock_cfg, monkeypatch):
        """'type' (Windows cat) should execute on Windows."""
        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path",
            lambda path, default_root="agent", require_exists=False: (Path("file.txt"), None)
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="file contents\n", stderr="", returncode=0
            )
            result = _shell_exec("type file.txt")
            assert "file contents" in result

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only command (copy)")
    def test_shell_exec_copy_command(self, mock_cfg, monkeypatch):
        """'copy' (Windows cp) should execute on Windows."""
        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path",
            lambda path, default_root="agent", require_exists=False: (Path("src.txt"), None)
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="1 file(s) copied.\n", stderr="", returncode=0
            )
            result = _shell_exec("copy src.txt dst.txt")
            assert "copied" in result

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only command (move)")
    def test_shell_exec_move_command(self, mock_cfg, monkeypatch):
        """'move' (Windows mv) should execute on Windows."""
        monkeypatch.setattr(
            "tools.cli_ops.helpers.resolve_path",
            lambda path, default_root="agent", require_exists=False: (Path("src.txt"), None)
        )
        monkeypatch.setattr(
            "tools.cli_ops.helpers._is_within", lambda resolved, root: True
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="1 file(s) moved.\n", stderr="", returncode=0
            )
            result = _shell_exec("move src.txt dst.txt")
            assert "moved" in result

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only command (del)")
    def test_shell_exec_del_command(self, mock_cfg, monkeypatch):
        """'del' (Windows rm) should be rejected — not in allowlist.

        NOTE: 'del' is a Windows shell builtin, not a binary, so even if it
        were in the allowlist, subprocess.run(shell=False) would fail with
        FileNotFoundError. The system.py help text mentions 'del <file>',
        but the allowlist does NOT include 'del' — this is a pre-existing
        inconsistency documented by this test.
        """
        result = _shell_exec("del file.txt")
        # 'del' is not in ALLOWED_COMMANDS, so the allowlist check rejects it.
        assert "not in the allowlist" in result
        assert "del" in result

    def test_shell_exec_windows_command_mapping(self, mock_cfg, monkeypatch):
        """Windows command mapping logic should recognize 'dir' even on Linux.

        Mocks os.name='nt' to simulate Windows, then verifies that 'dir'
        passes the allowlist check (it's in ALLOWED_COMMANDS). The actual
        subprocess call is mocked so no real binary execution happens.
        """
        # Mock os.name to simulate Windows. This affects shlex parsing
        # (posix=False on Windows) but NOT the allowlist check.
        monkeypatch.setattr("os.name", "nt")

        # Sanity check: Windows commands are in the allowlist
        assert "dir" in ALLOWED_COMMANDS
        assert "type" in ALLOWED_COMMANDS
        assert "copy" in ALLOWED_COMMANDS
        assert "move" in ALLOWED_COMMANDS

        # 'dir' with no args: no path validation tokens, should reach
        # subprocess.run. Mock subprocess to avoid actually running 'dir'.
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Volume in drive C\n Directory of C:\\test\n", stderr="", returncode=0
            )
            result = _shell_exec("dir")
            # Should NOT be rejected by allowlist
            assert "not in the allowlist" not in result
            # Should have invoked subprocess (the mock)
            mock_run.assert_called_once()
