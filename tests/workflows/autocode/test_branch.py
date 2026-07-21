"""tests/workflows/autocode/test_branch.py
Tests for node_git_branch — branch creation, git scoping, and error handling.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from pathlib import Path


@pytest.fixture
def temp_agent_root(tmp_path, monkeypatch):
    """Patch cfg.agent_root to a temp directory for safe fallback testing."""
    import core.config
    monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)
    yield tmp_path


class TestGitOpsFallback:
    """When project_root is empty/None, git ops must use cfg.agent_root."""

    def test_commit_fallback_to_agent_root(self, temp_agent_root):
        from workflows.autocode_impl.git_ops import _git_commit
        # [v3.10 / centralize-utils Phase B] _git_commit is now a direct alias
        # for `workflow_helpers.commit` — signature is
        # (project_root, message, target_file="", tid). It uses `_git()`
        # (3 calls: add, commit, rev-parse) instead of the `git()` facade
        # (2 calls: status, commit).
        #
        # When project_root="", commit() returns {committed: False, reason:
        # "no project_root"} — it does NOT fall back to cfg.agent_root (the
        # old vcs_ops._git_commit did, but the new helper is stricter).
        # So we test the empty-project_root path returns the structured dict.
        result = _git_commit("", "test commit", tid="t2")
        assert result["committed"] is False
        assert "no project_root" in result.get("reason", "")


class TestGitOpsOverride:
    """When project_root is set, git ops must route to it."""

    def test_commit_uses_project_root(self, tmp_path):
        from workflows.autocode_impl.git_ops import _git_commit
        custom_root = tmp_path / "workspace_project"
        custom_root.mkdir()
        # [v3.10 / centralize-utils Phase B] New signature + _git() runner.
        # Patch _git (the workflow_helpers runner) — 3 calls: add, commit,
        # rev-parse --short HEAD.
        with patch("tools.git_ops.workflow_helpers._git") as mock_git:
            mock_git.side_effect = [
                (0, "", ""),                          # git add -A
                (0, "[master def456]", ""),            # git commit
                (0, "def456\n", ""),                    # git rev-parse --short HEAD
            ]
            result = _git_commit(str(custom_root), "override commit", tid="t4")
            assert result["sha"] == "def456"
            assert result["committed"] is True
            # All _git calls must use custom_root as cwd.
            for call in mock_git.call_args_list:
                assert call[0][1] == custom_root


class TestNodeGitBranchScoping:
    """node_git_branch must pass project_root to git_ops."""

    def test_branch_routes_to_project_root(self, tmp_path):
        from workflows.autocode_impl.nodes.branch import node_git_branch
        custom_root = str(tmp_path / "scoped_repo")
        # [v3.0] Use _default_state() so vcs sub-state is populated.
        # Then override branch in the vcs sub-state ONLY (no flat mirror).
        from workflows.autocode_impl.state import _default_state
        state = _default_state(task="branch test")
        state["trace_id"] = "t5"
        state["status"] = "running"
        state["project_root"] = custom_root
        state["vcs"] = dict(state.get("vcs", {}))
        state["vcs"]["branch"] = "feat/scoped"  # sub-state (primary, only)
        with patch("workflows.autocode_impl.nodes.branch._git_create_branch") as mock_branch:
            mock_branch.return_value = True
            node_git_branch(state)
            mock_branch.assert_called_once()
            # [v3.10 / centralize-utils Phase B] New signature:
            # create_branch(project_root, branch, tid) — project_root is FIRST.
            # call_args[0] = (project_root, branch, tid)
            assert mock_branch.call_args[0][0] == custom_root  # project_root
            assert mock_branch.call_args[0][1] == "feat/scoped"  # branch


class TestNodeGitBranchErrorHandling:
    """[P1 #10] node_git_branch must return error on branch creation failure."""

    def test_returns_error_on_failure(self, tmp_path):
        from workflows.autocode_impl.nodes.branch import node_git_branch
        # [v3.0] Use _default_state() so vcs sub-state is populated.
        from workflows.autocode_impl.state import _default_state
        state = _default_state(task="branch fail")
        state["trace_id"] = "t1"
        state["status"] = "running"
        state["vcs"] = dict(state.get("vcs", {}))
        state["vcs"]["branch"] = "feat/broken"  # sub-state (primary, only)
        with patch("workflows.autocode_impl.nodes.branch._git_create_branch", return_value=False):
            result = node_git_branch(state)
            assert result["status"] == "error"
            assert "Failed to create git branch" in result["error"]


class TestNoGitSnapshot:
    """[Bug #2] _git_snapshot was removed — branch node must not call it."""

    def test_git_ops_has_no_snapshot_function(self):
        import workflows.autocode_impl.git_ops as git_ops
        assert not hasattr(git_ops, "_git_snapshot"), "_git_snapshot must be removed"

    def test_branch_node_no_snapshot_call(self, tmp_path):
        """branch.py source must not call _git_snapshot (comments are OK)."""
        import inspect, ast
        from workflows.autocode_impl.nodes.branch import node_git_branch
        source = inspect.getsource(node_git_branch)
        # Strip comments and docstrings before checking
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant,))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
        code_str = "\n".join(code_lines)
        assert "_git_snapshot" not in code_str, "branch node must not call _git_snapshot"
