"""Real integration tests using actual git repositories on disk."""
import subprocess
import pytest
from pathlib import Path
from tools.git import git


@pytest.fixture
def fresh_repo(tmp_path):
    """Provide a clean temporary directory. DO NOT init git here; the test verifies git(operation='init')."""
    return tmp_path


class TestRealGitLifecycle:
    """Test a complete git workflow: init → edit → snapshot → commit → branch → checkout → rollback."""

    def test_full_lifecycle(self, fresh_repo):
        repo = fresh_repo
        root = str(repo)

        # 1. Init
        r_init = git(operation="init", root=root)
        assert r_init["status"] == "initialised"
        assert (repo / ".gitignore").exists()

        # 2. Status (clean)
        r_status = git(operation="status", root=root)
        assert r_status["status"] == "ok"
        assert r_status["clean"] is True

        # 3. Modify file & Diff
        # Note: git diff only shows changes to TRACKED files.
        # .gitignore was committed by init, so modifying it triggers diff.
        (repo / ".gitignore").write_text("# modified\n__pycache__/\n*.pyc\n", encoding="utf-8")
        r_diff = git(operation="diff", root=root)
        assert r_diff["status"] == "ok"
        assert r_diff["has_changes"] is True

        # 4. Snapshot (create app.py for the rest of the lifecycle)
        (repo / "app.py").write_text("print('v1')", encoding="utf-8")
        r_snap = git(operation="snapshot", message="before v2", root=root)
        assert r_snap["status"] == "committed"
        assert "before v2" in r_snap["message"]

        # 5. Modify again & Commit
        (repo / "app.py").write_text("print('v2')", encoding="utf-8")
        r_commit = git(operation="commit", message="feat: upgrade to v2", root=root)
        assert r_commit["status"] == "committed"

        # 6. Log
        r_log = git(operation="log", n=5, root=root)
        assert r_log["status"] == "ok"
        assert r_log["count"] >= 2  # initial + snapshot + commit
        messages = [c["message"] for c in r_log["commits"]]
        assert any("v2" in m for m in messages)

        # 7. Branch & Checkout
        git(operation="branch", message="create experimental", root=root)
        r_checkout = git(operation="checkout", message="experimental", root=root)
        assert r_checkout["status"] == "switched"

        # 8. Tag
        r_tag = git(operation="tag", message="create v2.0", root=root)
        assert r_tag["status"] == "created"

        # 9. Show
        r_show = git(operation="show", message="v2.0", root=root)
        assert r_show["status"] == "ok"
        assert "v2.0" in r_show["output"] or "v2" in r_show["output"]

        # 10. Rollback (safe)
        (repo / "app.py").write_text("print('broken')", encoding="utf-8")
        r_rollback = git(operation="rollback", root=root)
        assert r_rollback["status"] == "rolled_back"
        # Verify file restored to HEAD
        assert "broken" not in (repo / "app.py").read_text(encoding="utf-8")

        # 11. Restore specific file
        (repo / "app.py").write_text("print('corrupted')", encoding="utf-8")
        r_restore = git(operation="restore", path="app.py", root=root)
        assert r_restore["status"] == "restored"
        assert "corrupted" not in (repo / "app.py").read_text(encoding="utf-8")


class TestRealErrorHandling:
    """Test that git operations fail gracefully with clear messages."""

    def test_commit_without_repo(self, tmp_path):
        result = git(operation="commit", message="fail", root=str(tmp_path))
        assert result["status"] == "error"
        assert "not a git repository" in result["error"].lower()

    def test_checkout_missing_target(self, fresh_repo):
        # Init repo first so dispatcher passes the needs_repo check
        git(operation="init", root=str(fresh_repo))
        result = git(operation="checkout", root=str(fresh_repo))
        assert result["status"] == "error"
        assert "required" in result["error"].lower()

    def test_tag_create_missing_name(self, fresh_repo):
        result = git(operation="tag", message="create", root=str(fresh_repo))
        assert result["status"] == "error"
        assert "Tag name required" in result["error"]