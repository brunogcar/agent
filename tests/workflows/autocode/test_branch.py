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
        with patch("tools.git.git") as mock_git:
            mock_git.side_effect = [
                {"status": "ok", "count": 1},
                {"status": "committed", "commit_hash": "abc123"},
            ]
            # [v1.4 P1] _git_commit now returns a dict with {committed, sha}.
            result = _git_commit("test commit", tid="t2", project_root="")
            assert result["sha"] == "abc123"
            assert result["committed"] is True
            for call in mock_git.call_args_list:
                assert call[1]["root"] == str(temp_agent_root)


class TestGitOpsOverride:
    """When project_root is set, git ops must route to it."""

    def test_commit_uses_project_root(self, tmp_path):
        from workflows.autocode_impl.git_ops import _git_commit
        custom_root = str(tmp_path / "workspace_project")
        with patch("tools.git.git") as mock_git:
            mock_git.side_effect = [
                {"status": "ok", "count": 2},
                {"status": "committed", "commit_hash": "def456"},
            ]
            # [v1.4 P1] _git_commit now returns a dict with {committed, sha}.
            result = _git_commit("override commit", tid="t4", project_root=custom_root)
            assert result["sha"] == "def456"
            assert result["committed"] is True
            for call in mock_git.call_args_list:
                assert call[1]["root"] == custom_root


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
            assert mock_branch.call_args[0][2] == custom_root


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
