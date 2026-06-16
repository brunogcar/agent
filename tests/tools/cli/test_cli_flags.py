"""Unit tests for CLI dangerous flag blocking.

[BUGFIX-3] Covers the BLOCKED_FLAGS check in _shell_exec.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.cli_ops.helpers import _shell_exec


@pytest.fixture(autouse=True)
def mock_cfg():
    """Mock cfg to prevent AsyncMock leakage from other tests."""
    with patch("tools.cli_ops.helpers.cfg") as mock_cfg:
        mock_cfg.cli_max_command_chars = 4096
        mock_cfg.cli_max_arguments = 50
        mock_cfg.workspace_root = MagicMock()
        mock_cfg.workspace_root.resolve.return_value = MagicMock()
        mock_cfg.workspace_root.resolve.return_value.__eq__ = lambda self, other: False
        mock_cfg.workspace_root.resolve.return_value.parents = []
        yield mock_cfg


class TestBlockedFlags:
    """Verify dangerous flags are rejected even for allowlisted commands."""

    @pytest.mark.parametrize("flag", ["-c", "-m", "--command", "--module", "-e", "--eval"])
    def test_python_blocked_flags(self, flag):
        """python with dangerous flags must be rejected."""
        result = _shell_exec(f"python {flag} 'print(1)'")
        assert "blocked for security" in result.lower()

    def test_python_c_flag_arbitrary_code(self):
        """The classic attack vector: python -c 'import os; os.system(...)'."""
        result = _shell_exec('python -c "import os; os.system(\'rm -rf /\')"')
        assert "blocked for security" in result.lower()
        # Must NOT execute the dangerous command
        assert "rm -rf" not in result.lower() or "blocked" in result.lower()

    def test_python_m_flag_module_execution(self):
        """python -m can execute arbitrary modules (e.g., http.server)."""
        result = _shell_exec("python -m http.server")
        assert "blocked for security" in result.lower()

    def test_gh_cli_eval_flag(self):
        """gh --eval could be used for injection."""
        result = _shell_exec("gh --eval 'malicious'")
        assert "blocked for security" in result.lower()

    def test_git_command_with_blocked_flag(self):
        """Even git with -c (config injection) should be blocked."""
        result = _shell_exec("git -c core.editor='vim -- /etc/passwd' status")
        assert "blocked for security" in result.lower()

    def test_safe_flags_not_blocked(self):
        """Common safe flags must still work."""
        # These should NOT be in BLOCKED_FLAGS
        safe_flags = ["-la", "-l", "-a", "-v", "--version", "-h", "--help"]
        for flag in safe_flags:
            result = _shell_exec(f"ls {flag}")
            # Should NOT contain "blocked for security"
            assert "blocked for security" not in result.lower(), f"Flag {flag} was incorrectly blocked"
