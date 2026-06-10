"""Test git action patterns and basic functionality."""
import subprocess
import pytest
from tools.git import git


@pytest.fixture(autouse=True)
def _use_temp_roots(monkeypatch, tmp_path):
    """Redirect agent_root and workspace_root to tmp_path (a real Path object) so path guard allows tests."""
    monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)
    monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
    """Bypass path guard by replacing resolve_path with a permissive version."""
    import pathlib
    def _fake_resolve(path, default_root="agent", require_exists=False):
        p = pathlib.Path(str(path))
        return (p, "")
    monkeypatch.setattr("core.path_guard.resolve_path", _fake_resolve)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@agent.local"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=repo, check=True, capture_output=True)
    (repo / "file.txt").write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


class TestStatusPatterns:
    def test_status_clean(self, git_repo):
        result = git(action="status", root=str(git_repo))
        assert result["status"] == "success"
        assert result["clean"] is True
        assert result["count"] == 0

    def test_status_with_changes(self, git_repo):
        (git_repo / "file.txt").write_text("modified", encoding="utf-8")
        result = git(action="status", root=str(git_repo))
        assert result["status"] == "success"
        assert result["clean"] is False
        assert result["count"] > 0


class TestLogPatterns:
    def test_log_default(self, git_repo):
        result = git(action="log", root=str(git_repo))
        assert result["status"] == "success"
        assert result["count"] == 1
        assert "initial" in result["commits"][0]["message"]

    def test_log_custom_limit(self, git_repo):
        result = git(action="log", n=1, root=str(git_repo))
        assert result["status"] == "success"
        assert result["count"] <= 1


class TestDiffPatterns:
    def test_diff_no_changes(self, git_repo):
        result = git(action="diff", root=str(git_repo))
        assert result["status"] == "success"
        assert result["has_changes"] is False

    def test_diff_with_changes(self, git_repo):
        (git_repo / "file.txt").write_text("changed content", encoding="utf-8")
        result = git(action="diff", root=str(git_repo))
        assert result["status"] == "success"
        assert result["has_changes"] is True
        assert "changed content" in result["diff"]


class TestCommitPatterns:
    def test_commit_success(self, git_repo):
        (git_repo / "file.txt").write_text("commit this", encoding="utf-8")
        result = git(action="commit", message="test commit", root=str(git_repo))
        assert result["status"] == "committed"
        assert "commit_hash" in result

    def test_commit_nothing_to_commit(self, git_repo):
        result = git(action="commit", message="empty commit", root=str(git_repo))
        assert result["status"] == "nothing_to_commit"

    def test_commit_missing_message(self, git_repo):
        result = git(action="commit", root=str(git_repo))
        assert result["status"] == "error"
        assert "message is required" in result["error"]


class TestInitPatterns:
    def test_init_new_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "tools.git_ops.actions.init._check_repo",
            lambda cwd: (False, ""),
        )
        new_repo = tmp_path / "init_test"
        new_repo.mkdir()
        result = git(action="init", root=str(new_repo))
        assert result["status"] == "initialised"
        assert "commit_hash" in result
        assert (new_repo / ".gitignore").exists()

    def test_init_existing_repo(self, git_repo):
        result = git(action="init", root=str(git_repo))
        assert result["status"] == "already_a_repo"


class TestSnapshotPatterns:
    def test_snapshot_creates_commit(self, git_repo):
        (git_repo / "file.txt").write_text("snapshot test", encoding="utf-8")
        result = git(action="snapshot", message="pre-edit", root=str(git_repo))
        assert result["status"] == "committed"
        assert "pre-edit" in result["message"]

    def test_snapshot_clean_tree(self, git_repo):
        result = git(action="snapshot", root=str(git_repo))
        assert result["status"] == "nothing_to_commit"


class TestRollbackPatterns:
    def test_rollback_safe_stash(self, git_repo):
        (git_repo / "file.txt").write_text("rollback test", encoding="utf-8")
        result = git(action="rollback", root=str(git_repo))
        assert result["status"] == "rolled_back"
        assert "stash" in result["message"].lower() or result["stash_ref"] != ""

    def test_rollback_force(self, git_repo):
        (git_repo / "untracked.txt").write_text("delete me", encoding="utf-8")
        result = git(action="rollback", force=True, root=str(git_repo))
        assert result["status"] == "rolled_back"
        assert "permanently discarded" in result["message"]


class TestRestorePatterns:
    def test_restore_file(self, git_repo):
        (git_repo / "file.txt").write_text("broken", encoding="utf-8")
        result = git(action="restore", path="file.txt", root=str(git_repo))
        assert result["status"] == "restored"
        assert (git_repo / "file.txt").read_text(encoding="utf-8") == "initial content"

    def test_restore_missing_path(self, git_repo):
        result = git(action="restore", root=str(git_repo))
        assert result["status"] == "error"
        assert "File path is required" in result["error"]


class TestShowPatterns:
    def test_show_head(self, git_repo):
        result = git(action="show", root=str(git_repo))
        assert result["status"] == "success"
        assert "initial" in result["output"]

    def test_show_specific_commit(self, git_repo):
        log = git(action="log", n=1, root=str(git_repo))
        head_hash = log["commits"][0]["hash"]
        result = git(action="show", message=head_hash, root=str(git_repo))
        assert result["status"] == "success"


class TestTagPatterns:
    def test_tag_list(self, git_repo):
        result = git(action="tag", root=str(git_repo))
        assert result["status"] == "success"
        assert isinstance(result["tags"], list)

    def test_tag_create(self, git_repo):
        result = git(action="tag", message="create v1.0", root=str(git_repo))
        assert result["status"] == "created"
        assert result["tag"] == "v1.0"


class TestBranchPatterns:
    def test_branch_list(self, git_repo):
        result = git(action="branch", root=str(git_repo))
        assert result["status"] == "success"
        assert any(b["current"] for b in result["branches"])

    def test_branch_create(self, git_repo):
        result = git(action="branch", message="create feature-x", root=str(git_repo))
        assert result["status"] == "created"
        assert result["branch"] == "feature-x"

    def test_branch_delete(self, git_repo):
        git(action="branch", message="create temp-branch", root=str(git_repo))
        result = git(action="branch", message="delete temp-branch", root=str(git_repo))
        assert result["status"] == "deleted"


class TestCheckoutPatterns:
    def test_checkout_switch(self, git_repo):
        git(action="branch", message="create dev", root=str(git_repo))
        result = git(action="checkout", message="dev", root=str(git_repo))
        assert result["status"] == "switched"
        assert result["to"] == "dev"

    def test_checkout_create_and_switch(self, git_repo):
        result = git(action="checkout", message="-b new-feature", root=str(git_repo))
        assert result["status"] == "switched"
        assert result["branch"] == "new-feature"