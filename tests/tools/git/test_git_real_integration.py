"""Real integration tests using actual git repositories on disk.

These tests exercise the full git tool lifecycle with real git operations.
No mocking — every call runs actual git commands in a temp repo.
"""
from __future__ import annotations

import subprocess
import pytest
from tools.git import git


@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch, tmp_path):
    """Redirect agent_root and workspace_root to tmp_path.
    Bypass path_guard for test safety.
    """
    monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)
    monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)

    import pathlib
    def _fake_resolve(path, default_root="agent", require_exists=False):
        p = pathlib.Path(str(path))
        return (p, "")
    monkeypatch.setattr("core.path_guard.resolve_path", _fake_resolve)


@pytest.fixture
def fresh_repo(tmp_path):
    """Provide a clean temporary directory."""
    repo = tmp_path / "fresh"
    repo.mkdir()
    return repo


class TestRealGitLifecycle:
    """Full lifecycle: init → status → modify → diff → snapshot → commit → log → branch → tag → show → rollback → restore."""

    def test_full_lifecycle(self, fresh_repo, monkeypatch):
        repo = fresh_repo
        root = str(repo)

        monkeypatch.setattr(
            "tools.git_ops.actions.init._check_repo",
            lambda cwd: (False, ""),
        )

        # 1. Init
        r_init = git(action="init", root=root)
        assert r_init["status"] == "initialised"
        assert (repo / ".gitignore").exists()

        # 2. Status (clean)
        r_status = git(action="status", root=root)
        assert r_status["status"] == "success"
        assert r_status["clean"] is True

        # 3. Modify file & Diff
        (repo / ".gitignore").write_text("# modified\n__pycache__/\n*.pyc\n", encoding="utf-8")
        r_diff = git(action="diff", root=root)
        assert r_diff["status"] == "success"
        assert r_diff["has_changes"] is True

        # 4. Snapshot
        (repo / "app.py").write_text("print('v1')", encoding="utf-8")
        r_snap = git(action="snapshot", message="before v2", root=root)
        assert r_snap["status"] == "committed"
        assert "before v2" in r_snap["message"]

        # 5. Modify again & Commit
        (repo / "app.py").write_text("print('v2')", encoding="utf-8")
        r_commit = git(action="commit", message="feat: upgrade to v2", root=root)
        assert r_commit["status"] == "committed"

        # 6. Log
        r_log = git(action="log", n=5, root=root)
        assert r_log["status"] == "success"
        assert r_log["count"] >= 2
        messages = [c["message"] for c in r_log["commits"]]
        assert any("v2" in m for m in messages)

        # 7. Branch & Checkout (new atomic actions)
        # Note: git init default branch is 'master'
        git(action="branch_create", target="experimental", root=root)
        r_checkout = git(action="checkout_branch", target="experimental", root=root)
        assert r_checkout["status"] == "switched"
        assert r_checkout["to"] == "experimental"

        # 8. Tag
        r_tag = git(action="tag_create", target="v2.0", root=root)
        assert r_tag["status"] == "created"

        # 9. Show (target param, not message)
        r_show = git(action="show", target="v2.0", root=root)
        assert r_show["status"] == "success"

        # 10. Rollback (safe)
        (repo / "app.py").write_text("print('broken')", encoding="utf-8")
        r_rollback = git(action="rollback", root=root)
        assert r_rollback["status"] == "rolled_back"
        assert "broken" not in (repo / "app.py").read_text(encoding="utf-8")

        # 11. Restore specific file
        (repo / "app.py").write_text("print('corrupted')", encoding="utf-8")
        r_restore = git(action="restore", path="app.py", root=root)
        assert r_restore["status"] == "restored"
        assert "corrupted" not in (repo / "app.py").read_text(encoding="utf-8")

        # 12. Branch list
        r_branches = git(action="branch_list", root=root)
        assert r_branches["status"] == "success"
        names = [b["name"] for b in r_branches["branches"]]
        assert "experimental" in names

        # 13. Tag list
        r_tags = git(action="tag_list", root=root)
        assert r_tags["status"] == "success"
        assert "v2.0" in r_tags["tags"]

        # 14. Tag delete
        r_del = git(action="tag_delete", target="v2.0", root=root)
        assert r_del["status"] == "deleted"


class TestRealErrorHandling:
    """Error cases with real repos."""

    def test_commit_without_repo(self, tmp_path, monkeypatch):
        """Commit in non-repo should fail with repo error."""
        monkeypatch.setattr(
            "tools.git._check_repo",
            lambda cwd: (False, "not a git repository"),
        )
        non_repo = tmp_path / "non_repo"
        non_repo.mkdir()
        result = git(action="commit", message="fail", root=str(non_repo))
        assert result["status"] == "error"
        assert "not a git repository" in result["error"].lower()

    def test_checkout_branch_missing_target(self, fresh_repo, monkeypatch):
        """checkout_branch without target should error."""
        monkeypatch.setattr(
            "tools.git_ops.actions.init._check_repo",
            lambda cwd: (False, ""),
        )
        git(action="init", root=str(fresh_repo))
        result = git(action="checkout_branch", root=str(fresh_repo))
        assert result["status"] == "error"
        assert "required" in result["error"].lower()

    def test_tag_create_missing_name(self, fresh_repo, monkeypatch):
        """tag_create without target should error (in an initialized repo)."""
        monkeypatch.setattr(
            "tools.git_ops.actions.init._check_repo",
            lambda cwd: (False, ""),
        )
        git(action="init", root=str(fresh_repo))
        result = git(action="tag_create", root=str(fresh_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]
