"""Tests for CLI flag blocking in tools/cli_ops/helpers.py.

[BUGFIX-SECURITY] Verifies that the flag blacklist catches:
  - Standard flag syntax: -c, -m, --command, --module, -e, --eval
  - Equals syntax: --command=..., -c=...
  - Combined short flags: -cm, -ce
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.cli_ops.helpers import _shell_exec


@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch):
    """Mock cfg for all tests in this file to avoid .env dependency."""
    mock = MagicMock()
    mock.cli_max_command_chars = 4096
    mock.cli_max_arguments = 20
    # Use a real Path for workspace_root so path resolution works on Windows
    mock.workspace_root = Path(os.getcwd())
    monkeypatch.setattr("tools.cli_ops.helpers.cfg", mock)


class TestCLIFlagBlocking:
    """Dangerous flags must be blocked in all syntax variants."""

    def test_standard_flag_c_blocked(self):
        """python -c must be blocked."""
        result = _shell_exec('python -c "import os"')
        assert "blocked for security" in result
        assert "-c" in result

    def test_standard_flag_m_blocked(self):
        """python -m must be blocked."""
        result = _shell_exec("python -m http.server")
        assert "blocked for security" in result
        assert "-m" in result

    def test_standard_flag_command_blocked(self):
        """python --command must be blocked."""
        result = _shell_exec("python --command import os")
        assert "blocked for security" in result
        assert "--command" in result

    def test_standard_flag_module_blocked(self):
        """python --module must be blocked."""
        result = _shell_exec("python --module http.server")
        assert "blocked for security" in result
        assert "--module" in result

    def test_standard_flag_eval_blocked(self):
        """python -e must be blocked."""
        result = _shell_exec("python -e 'print(1)'")
        assert "blocked for security" in result
        assert "-e" in result

    def test_standard_flag_eval_long_blocked(self):
        """python --eval must be blocked."""
        result = _shell_exec("python --eval 'print(1)'")
        assert "blocked for security" in result
        assert "--eval" in result


class TestCLIFlagEqualsBypass:
    """Equals-syntax bypasses must be blocked."""

    def test_command_equals_blocked(self):
        """python --command=import os must be blocked."""
        result = _shell_exec("python --command=import os; os.system('dir')")
        assert "blocked for security" in result
        assert "--command=" in result

    def test_module_equals_blocked(self):
        """python --module=http.server must be blocked."""
        result = _shell_exec("python --module=http.server")
        assert "blocked for security" in result
        assert "--module=" in result

    def test_c_equals_blocked(self):
        """python -c=print(1) must be blocked."""
        result = _shell_exec("python -c=print(1)")
        assert "blocked for security" in result
        assert "-c=" in result

    def test_m_equals_blocked(self):
        """python -m=http.server must be blocked."""
        result = _shell_exec("python -m=http.server")
        assert "blocked for security" in result
        assert "-m=" in result


class TestCLIFlagCombinedBypass:
    """Combined short flag bypasses must be blocked."""

    def test_combined_cm_blocked(self):
        """python -cm http.server must be blocked (interprets as -c m)."""
        result = _shell_exec("python -cm http.server")
        assert "blocked for security" in result
        assert "-cm" in result

    def test_combined_ce_blocked(self):
        """python -ce print(1) must be blocked."""
        result = _shell_exec("python -ce print(1)")
        assert "blocked for security" in result
        assert "-ce" in result


class TestCLISafeFlags:
    """Safe flags must NOT be blocked."""

    def test_safe_version_flag_allowed(self):
        """python --version must be allowed."""
        # This will fail at subprocess level (no real python), but should NOT
        # be blocked by flag check
        result = _shell_exec("python --version")
        assert "blocked for security" not in result

    def test_safe_help_flag_allowed(self):
        """python --help must be allowed."""
        result = _shell_exec("python --help")
        assert "blocked for security" not in result
