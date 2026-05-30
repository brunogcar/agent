"""
tests/workflows/autocode/test_git_scoping.py
Validates project_root isolation for git_ops, branch, and commit nodes.
Guarantees:
- All git calls route to project_root when set
- Falls back to cfg.agent_root when project_root is empty/None
- No real git operations; tools.git.git and subprocess.run are mocked
- cfg.agent_root is patched to tmp_path for safety
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture
def temp_agent_root(tmp_path, monkeypatch):
    """Patch cfg.agent_root to a temp directory for safe fallback testing."""
    import core.config
    original = core.config.cfg.agent_root
    monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)
    yield tmp_path
    # monkeypatch auto-restores after test


@pytest.fixture
def base_state(temp_agent_root):
    """Minimal state for git scoping tests."""
    return {
        "task": "test git scoping",
        "trace_id": "test-trace-git",
        "status": "running",
        "project_root": str(temp_agent_root),
        "branch": "",
        "verification_passed": True,
        "plan": [],
    }


class TestGitOpsFallback:
    """When project_root is empty/None, git ops must use cfg.agent_root."""

    def test_snapshot_fallback_to_agent_root(self, temp_agent_root):
        from workflows.autocode_helpers.git_ops import _git_snapshot
        with patch("tools.git.git") as mock_git:
            mock_git.return_value = {"status": "nothing_to_commit"}
            _git_snapshot("test fallback", tid="t1", project_root=None)
            call_kwargs = mock_git.call_args[1]
            assert call_kwargs["root"] == str(temp_agent_root)

    def test_commit_fallback_to_agent_root(self, temp_agent_root):
        from workflows.autocode_helpers.git_ops import _git_commit
        with patch("tools.git.git") as mock_git:
            mock_git.side_effect = [
                {"status": "ok", "count": 1},
                {"status": "committed", "commit_hash": "abc123"},
            ]
            sha = _git_commit("test commit", tid="t2", project_root="")
            assert sha == "abc123"
            # Both status and commit calls should use agent_root
            for call in mock_git.call_args_list:
                assert call[1]["root"] == str(temp_agent_root)


class TestGitOpsOverride:
    """When project_root is set, git ops must route to it."""

    def test_snapshot_uses_project_root(self, tmp_path):
        from workflows.autocode_helpers.git_ops import _git_snapshot
        custom_root = str(tmp_path / "workspace_project")
        with patch("tools.git.git") as mock_git:
            mock_git.return_value = {"status": "committed"}
            _git_snapshot("test override", tid="t3", project_root=custom_root)
            assert mock_git.call_args[1]["root"] == custom_root

    def test_commit_uses_project_root(self, tmp_path):
        from workflows.autocode_helpers.git_ops import _git_commit
        custom_root = str(tmp_path / "workspace_project")
        with patch("tools.git.git") as mock_git:
            mock_git.side_effect = [
                {"status": "ok", "count": 2},
                {"status": "committed", "commit_hash": "def456"},
            ]
            sha = _git_commit("override commit", tid="t4", project_root=custom_root)
            assert sha == "def456"
            for call in mock_git.call_args_list:
                assert call[1]["root"] == custom_root


class TestNodeGitBranchScoping:
    """node_git_branch must pass project_root to git_ops."""

    def test_branch_node_routes_to_project_root(self, tmp_path):
        from workflows.autocode_helpers.nodes.branch import node_git_branch
        custom_root = str(tmp_path / "scoped_repo")
        state = {
            "task": "branch test",
            "trace_id": "t5",
            "status": "running",
            "project_root": custom_root,
            "branch": "feat/scoped",
        }
        # [FIX] Patch where the functions are USED (in branch module), not where defined
        with patch("workflows.autocode_helpers.nodes.branch._git_snapshot") as mock_snap, \
             patch("workflows.autocode_helpers.nodes.branch._git_create_branch") as mock_branch:
            mock_snap.return_value = True
            mock_branch.return_value = True
            node_git_branch(state)
            mock_snap.assert_called_once()
            assert mock_snap.call_args[0][2] == custom_root
            mock_branch.assert_called_once()
            assert mock_branch.call_args[0][2] == custom_root


class TestNodeCommitScoping:
    """node_commit must pass project_root to _git_commit."""

    def test_commit_node_routes_to_project_root(self, tmp_path):
        from workflows.autocode_helpers.nodes.commit import node_commit
        custom_root = str(tmp_path / "commit_repo")
        state = {
            "task": "commit test",
            "trace_id": "t6",
            "status": "running",
            "project_root": custom_root,
            "verification_passed": True,
            "plan": [{"label": "write_code"}],
            "task_type": "feature",
        }
        # [FIX] Patch where _git_commit is USED (in commit module)
        with patch("workflows.autocode_helpers.nodes.commit._git_commit") as mock_commit:
            mock_commit.return_value = "sha789"
            node_commit(state)
            mock_commit.assert_called_once()
            # Third positional arg is project_root
            assert mock_commit.call_args[0][2] == custom_root
