"""Tests for github push action.

push is the ONLY github action that does NOT use httpx — it shells out to
`git push` via subprocess. All tests mock subprocess.run to avoid touching
the real git remote.

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key:
  ok({"branch": "fix/timeout", ...}) -> {"status": "success", "data": {...}, "error": None}
So success assertions check `result["data"]["branch"]`, etc.

NOTE on subprocess patching:
  push.py does `import subprocess` then calls `subprocess.run(...)`.
  Because `subprocess` is imported as a module (not `from subprocess import run`),
  patching `tools.github_ops.actions.push.subprocess.run` intercepts the
  attribute lookup at call time — the patch is effective.
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


class TestPush:
    """push runs `git push origin <branch>` as a local subprocess."""

    def test_push_success(self):
        """Mock subprocess returns exit 0 — facade should return ok()."""
        with patch("tools.github_ops.actions.push.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(
                returncode=0,
                stdout="",
                stderr="To github.com:test-owner/test-repo.git\n   abc1234..def5678  fix/timeout -> fix/timeout\n",
            )
            result = github(action="push", branch="fix/timeout")

        assert result["status"] == "success"
        # ok() nests the action's payload under result["data"]
        data = result["data"]
        assert data["status"] == "ok"
        assert data["branch"] == "fix/timeout"
        assert data["remote"] == "origin"
        assert data["pushed"] is True
        assert data["forced"] is False
        assert "abc1234..def5678" in data["output"]
        assert "duration_ms" in result

        # Verify subprocess.run was called with a list (not shell=True)
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args")
        assert cmd == ["git", "push", "origin", "fix/timeout"]
        # Must NOT use shell=True — defense in depth against injection
        assert call_args[1].get("shell", False) is False

    def test_push_missing_branch(self):
        """Missing branch → fail() before any subprocess call."""
        with patch("tools.github_ops.actions.push.subprocess.run") as mock_run:
            result = github(action="push", branch="")

        assert result["status"] == "error"
        assert "branch is required" in result["error"]
        mock_run.assert_not_called()

    def test_push_force_uses_force_with_lease(self):
        """force=True must inject --force-with-lease (NOT --force) into cmd."""
        with patch("tools.github_ops.actions.push.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=0)
            result = github(action="push", branch="feat/rebase", force=True)

        assert result["status"] == "success"
        assert result["data"]["forced"] is True

        # Verify --force-with-lease is in the command, NOT --force
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--force-with-lease" in cmd
        assert "--force" not in cmd  # bare --force would be unsafe
        # --force-with-lease goes BEFORE the remote + branch
        assert cmd == ["git", "push", "--force-with-lease", "origin", "feat/rebase"]

    def test_push_subprocess_error(self):
        """Non-zero exit code from git push → fail() with exit_code + output."""
        with patch("tools.github_ops.actions.push.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(
                returncode=1,
                stdout="",
                stderr="! [rejected]    fix/timeout -> fix/timeout (fetch first)\n"
                       "error: failed to push some refs to 'github.com:test-owner/test-repo.git'\n",
            )
            result = github(action="push", branch="fix/timeout")

        assert result["status"] == "error"
        error_msg = result["error"]
        assert "exit 1" in error_msg
        # exit_code + output are attached as kwargs to fail()
        assert result.get("exit_code") == 1
        assert "rejected" in result.get("output", "")
        assert result.get("branch") == "fix/timeout"
