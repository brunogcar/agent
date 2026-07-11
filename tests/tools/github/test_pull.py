"""Tests for github pull action.

pull is a local git operation (subprocess), like push. All tests mock
subprocess.run to avoid touching the real git remote.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.github import github


def _make_completed_process(returncode: int = 0, stdout: str = "",
                            stderr: str = "") -> MagicMock:
    """Build a mock subprocess.CompletedProcess result."""
    cp = MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


class TestPull:
    """pull runs `git pull origin <branch>` as a local subprocess."""

    def test_pull_success_with_branch(self):
        """Mock subprocess returns exit 0 — facade should return ok()."""
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(
                returncode=0,
                stdout="",
                stderr="From github.com:test-owner/test-repo\n   abc1234..def5678  main -> origin/main\nUpdating abc1234..def5678\nFast-forward\n",
            )
            result = github(action="pull", branch="main")

        assert result["status"] == "success"
        data = result["data"]
        assert data["status"] == "ok"
        assert data["branch"] == "main"
        assert data["remote"] == "origin"
        assert data["pulled"] is True
        assert "abc1234..def5678" in data["output"]
        assert "duration_ms" in result

        # Verify subprocess.run was called with a list (not shell=True)
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args")
        assert cmd == ["git", "pull", "origin", "main"]
        assert call_args[1].get("shell", False) is False

    def test_pull_success_current_branch(self):
        """Empty branch → pulls current branch (git pull origin)."""
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(
                returncode=0,
                stdout="Already up to date.\n",
                stderr="",
            )
            result = github(action="pull")

        assert result["status"] == "success"
        assert result["data"]["branch"] == "(current)"
        assert result["data"]["pulled"] is True

        # Verify command is git pull origin (no branch)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "pull", "origin"]

    def test_pull_custom_remote(self):
        """Custom remote → passes through to git pull."""
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=0)
            result = github(action="pull", branch="main", remote="upstream")

        assert result["status"] == "success"
        assert result["data"]["remote"] == "upstream"
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "pull", "upstream", "main"]

    def test_pull_subprocess_error(self):
        """Non-zero exit code from git pull → fail() with exit_code + output."""
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(
                returncode=1,
                stdout="",
                stderr="error: Your local changes to the following files would be overwritten by merge:\n",
            )
            result = github(action="pull", branch="main")

        assert result["status"] == "error"
        assert "exit 1" in result["error"]
        assert result.get("exit_code") == 1
        assert "overwritten" in result.get("output", "")

    def test_pull_timeout(self):
        """subprocess.TimeoutExpired → fail() with timeout message."""
        import subprocess as sp
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            mock_run.side_effect = sp.TimeoutExpired(cmd="git pull", timeout=120)
            result = github(action="pull", branch="main")

        assert result["status"] == "error"
        assert "timed out" in result["error"].lower()

    def test_pull_git_not_found(self):
        """FileNotFoundError (git not installed) → fail() with install hint."""
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            result = github(action="pull", branch="main")

        assert result["status"] == "error"
        assert "git executable not found" in result["error"]

    def test_pull_forbidden_chars_in_branch(self):
        """Shell metacharacters in branch → fail() (defense in depth)."""
        with patch("tools.github_ops.actions.pull.subprocess.run") as mock_run:
            result = github(action="pull", branch="main; rm -rf /")

        assert result["status"] == "error"
        assert "forbidden character" in result["error"]
        mock_run.assert_not_called()
