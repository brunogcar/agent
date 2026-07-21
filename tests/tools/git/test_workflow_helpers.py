"""tests/tools/git/test_workflow_helpers.py — unit tests for
tools/git_ops/workflow_helpers.py.

9 tests covering:
  - commit_success (happy path: stage + commit + rev-parse returns SHA)
  - commit_nothing_to_commit (clean tree — commit detects "nothing to commit")
  - commit_exception (_git raises — caught + structured dict returned)
  - create_branch_success (checkout -b returns 0)
  - create_branch_already_exists_fallback (checkout -b fails with "already
    exists" → checkout <branch> fallback succeeds)
  - create_branch_failure (checkout -b fails with non-"already exists" error)
  - reset_hard_success (toplevel matches → reset + clean succeed)
  - reset_hard_toplevel_mismatch (toplevel != project_root → refuse)
  - reset_hard_no_project_root (empty project_root → refuse)

Phase B of the centralize-workflow-utils refactor (v1.2 of the git tool docs).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


class TestCommit:
    def test_commit_success(self, tmp_path):
        """Happy path — stage + commit + rev-parse → returns {committed, sha}."""
        from tools.git_ops.workflow_helpers import commit
        # _git is called 3 times: add (rc=0), commit (rc=0, out=""),
        # rev-parse --short HEAD (rc=0, out="abc1234").
        side = [
            (0, "", ""),  # git add
            (0, "[main abc1234] msg", ""),  # git commit
            (0, "abc1234", ""),  # git rev-parse --short HEAD
        ]
        with patch("tools.git_ops.workflow_helpers._git", side_effect=side) as m:
            result = commit(str(tmp_path), "test msg", "target.py", "tid1")
        assert result == {"committed": True, "sha": "abc1234"}
        assert m.call_count == 3
        # Verify the args of the first call (git add target.py)
        first_call_args = m.call_args_list[0][0][0]
        assert first_call_args == ["add", "target.py"]

    def test_commit_nothing_to_commit(self, tmp_path):
        """Clean tree — commit returns {committed: False, reason: nothing to commit}."""
        from tools.git_ops.workflow_helpers import commit
        # _git: add (rc=0), commit (rc=1, stderr contains "nothing to commit").
        side = [
            (0, "", ""),
            (1, "", "nothing to commit, working tree clean"),
        ]
        with patch("tools.git_ops.workflow_helpers._git", side_effect=side) as m:
            result = commit(str(tmp_path), "msg", "", "tid1")
        assert result["committed"] is False
        assert result["sha"] == ""
        assert "nothing to commit" in result["reason"]
        # Only 2 calls — rev-parse NOT called on nothing-to-commit.
        assert m.call_count == 2

    def test_commit_exception(self, tmp_path):
        """_git raises — commit catches + returns {committed: False, reason: error: ...}."""
        from tools.git_ops.workflow_helpers import commit
        with patch("tools.git_ops.workflow_helpers._git", side_effect=OSError("disk full")):
            result = commit(str(tmp_path), "msg", "", "tid1")
        assert result["committed"] is False
        assert result["sha"] == ""
        # The reason includes "error:" prefix.
        assert "error" in result["reason"].lower()
        assert "disk full" in result["reason"]


# ---------------------------------------------------------------------------
# create_branch
# ---------------------------------------------------------------------------


class TestCreateBranch:
    def test_create_branch_success(self, tmp_path):
        """checkout -b returns 0 → create_branch returns True."""
        from tools.git_ops.workflow_helpers import create_branch
        with patch("tools.git_ops.workflow_helpers._git", return_value=(0, "", "")) as m:
            result = create_branch(str(tmp_path), "feat/x", "tid1")
        assert result is True
        m.assert_called_once()
        # Verify the args: ["checkout", "-b", "feat/x"]
        args = m.call_args[0][0]
        assert args == ["checkout", "-b", "feat/x"]

    def test_create_branch_already_exists_fallback(self, tmp_path):
        """checkout -b fails with "already exists" → checkout <branch> succeeds."""
        from tools.git_ops.workflow_helpers import create_branch
        # First call (checkout -b) fails with "already exists"; second call
        # (checkout <branch>) succeeds.
        side = [
            (1, "", "fatal: a branch named 'feat/x' already exists"),
            (0, "", ""),
        ]
        with patch("tools.git_ops.workflow_helpers._git", side_effect=side) as m:
            result = create_branch(str(tmp_path), "feat/x", "tid1")
        assert result is True
        assert m.call_count == 2
        # Verify the second call was ["checkout", "feat/x"]
        second_call_args = m.call_args_list[1][0][0]
        assert second_call_args == ["checkout", "feat/x"]

    def test_create_branch_failure(self, tmp_path):
        """checkout -b fails with non-"already exists" error → returns False."""
        from tools.git_ops.workflow_helpers import create_branch
        with patch(
            "tools.git_ops.workflow_helpers._git",
            return_value=(1, "", "fatal: invalid branch name"),
        ) as m:
            result = create_branch(str(tmp_path), "feat/x", "tid1")
        assert result is False
        # Only 1 call — no fallback (error is not "already exists").
        m.assert_called_once()


# ---------------------------------------------------------------------------
# reset_hard
# ---------------------------------------------------------------------------


class TestResetHard:
    def test_reset_hard_success(self, tmp_path):
        """Toplevel matches → reset --hard + clean -fd succeed → returns True."""
        from tools.git_ops.workflow_helpers import reset_hard
        # 3 calls: rev-parse --show-toplevel (returns tmp_path), reset --hard,
        # clean -fd. All return 0.
        side = [
            (0, str(tmp_path) + "\n", ""),
            (0, "", ""),
            (0, "", ""),
        ]
        with patch("tools.git_ops.workflow_helpers._git", side_effect=side) as m:
            result = reset_hard(str(tmp_path), "tid1")
        assert result is True
        assert m.call_count == 3

    def test_reset_hard_toplevel_mismatch(self, tmp_path):
        """Toplevel != project_root → refuse + return False."""
        from tools.git_ops.workflow_helpers import reset_hard
        # rev-parse returns a DIFFERENT path → mismatch.
        different_path = str(tmp_path.parent / "other_repo")
        with patch(
            "tools.git_ops.workflow_helpers._git",
            return_value=(0, different_path + "\n", ""),
        ) as m:
            result = reset_hard(str(tmp_path), "tid1")
        assert result is False
        # Only 1 call (rev-parse) — reset + clean NOT called.
        m.assert_called_once()

    def test_reset_hard_no_project_root(self):
        """Empty project_root → refuse + return False (no _git call)."""
        from tools.git_ops.workflow_helpers import reset_hard
        with patch("tools.git_ops.workflow_helpers._git") as m:
            result = reset_hard("", "tid1")
        assert result is False
        # No _git call — refused before any git command.
        m.assert_not_called()
