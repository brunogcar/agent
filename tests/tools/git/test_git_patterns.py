"""Test git operation patterns and basic functionality."""
import subprocess
import pytest
from tools.git import git


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@agent.local"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "file.txt").write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestStatusPatterns:
    def test_status_clean(self, git_repo):
        result = git(operation="status", root=str(git_repo))
        assert result["status"] == "ok"
        assert result["clean"] is True
        assert result["count"] == 0

    def test_status_with_changes(self, git_repo):
        (git_repo / "file.txt").write_text("modified", encoding="utf-8")
        result = git(operation="status", root=str(git_repo))
        assert result["status"] == "ok"
        assert result["clean"] is False
        assert result["count"] > 0


class TestLogPatterns:
    def test_log_default(self, git_repo):
        result = git(operation="log", root=str(git_repo))
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert "initial" in result["commits"][0]["message"]

    def test_log_custom_limit(self, git_repo):
        result = git(operation="log", n=1, root=str(git_repo))
        assert result["status"] == "ok"
        assert result["count"] <= 1


class TestDiffPatterns:
    def test_diff_no_changes(self, git_repo):
        result = git(operation="diff", root=str(git_repo))
        assert result["status"] == "ok"
        assert result["has_changes"] is False

    def test_diff_with_changes(self, git_repo):
        (git_repo / "file.txt").write_text("changed content", encoding="utf-8")
        result = git(operation="diff", root=str(git_repo))
        assert result["status"] == "ok"
        assert result["has_changes"] is True
        assert "changed content" in result["diff"]


class TestCommitPatterns:
    def test_commit_success(self, git_repo):
        (git_repo / "file.txt").write_text("commit this", encoding="utf-8")
        result = git(operation="commit", message="test commit", root=str(git_repo))
        assert result["status"] == "committed"
        assert "commit_hash" in result

    def test_commit_nothing_to_commit(self, git_repo):
        result = git(operation="commit", message="empty commit", root=str(git_repo))
        assert result["status"] == "nothing_to_commit"

    def test_commit_missing_message(self, git_repo):
        result = git(operation="commit", root=str(git_repo))
        assert result["status"] == "error"
        assert "message is required" in result["error"]


class TestInitPatterns:
    def test_init_new_repo(self, tmp_path):
        result = git(operation="init", root=str(tmp_path))
        assert result["status"] == "initialised"
        assert "commit_hash" in result
        assert (tmp_path / ".gitignore").exists()

    def test_init_existing_repo(self, git_repo):
        result = git(operation="init", root=str(git_repo))
        assert result["status"] == "already_a_repo"


class TestSnapshotPatterns:
    def test_snapshot_creates_commit(self, git_repo):
        (git_repo / "file.txt").write_text("snapshot test", encoding="utf-8")
        result = git(operation="snapshot", message="pre-edit", root=str(git_repo))
        assert result["status"] == "committed"
        assert "pre-edit" in result["message"]

    def test_snapshot_clean_tree(self, git_repo):
        result = git(operation="snapshot", root=str(git_repo))
        assert result["status"] == "nothing_to_commit"


class TestRollbackPatterns:
    def test_rollback_safe_stash(self, git_repo):
        (git_repo / "file.txt").write_text("rollback test", encoding="utf-8")
        result = git(operation="rollback", root=str(git_repo))
        assert result["status"] == "rolled_back"
        assert "stash" in result["message"].lower() or result["stash_ref"] != ""

    def test_rollback_force(self, git_repo):
        (git_repo / "untracked.txt").write_text("delete me", encoding="utf-8")
        result = git(operation="rollback", force=True, root=str(git_repo))
        assert result["status"] == "rolled_back"
        assert "permanently discarded" in result["message"]


class TestRestorePatterns:
    def test_restore_file(self, git_repo):
        (git_repo / "file.txt").write_text("broken", encoding="utf-8")
        result = git(operation="restore", path="file.txt", root=str(git_repo))
        assert result["status"] == "restored"
        assert (git_repo / "file.txt").read_text(encoding="utf-8") == "initial content"

    def test_restore_missing_path(self, git_repo):
        result = git(operation="restore", root=str(git_repo))
        assert result["status"] == "error"
        assert "File path is required" in result["error"]


class TestShowPatterns:
    def test_show_head(self, git_repo):
        result = git(operation="show", root=str(git_repo))
        assert result["status"] == "ok"
        assert "initial" in result["output"]

    def test_show_specific_commit(self, git_repo):
        # Get HEAD hash
        log = git(operation="log", n=1, root=str(git_repo))
        head_hash = log["commits"][0]["hash"]
        result = git(operation="show", message=head_hash, root=str(git_repo))
        assert result["status"] == "ok"


class TestTagPatterns:
    def test_tag_list(self, git_repo):
        result = git(operation="tag", root=str(git_repo))
        assert result["status"] == "ok"
        assert isinstance(result["tags"], list)

    def test_tag_create(self, git_repo):
        result = git(operation="tag", message="create v1.0", root=str(git_repo))
        assert result["status"] == "created"
        assert result["tag"] == "v1.0"


class TestBranchPatterns:
    def test_branch_list(self, git_repo):
        result = git(operation="branch", root=str(git_repo))
        assert result["status"] == "ok"
        assert any(b["current"] for b in result["branches"])

    def test_branch_create(self, git_repo):
        result = git(operation="branch", message="create feature-x", root=str(git_repo))
        assert result["status"] == "created"
        assert result["branch"] == "feature-x"

    def test_branch_delete(self, git_repo):
        git(operation="branch", message="create temp-branch", root=str(git_repo))
        result = git(operation="branch", message="delete temp-branch", root=str(git_repo))
        assert result["status"] == "deleted"


class TestCheckoutPatterns:
    def test_checkout_switch(self, git_repo):
        git(operation="branch", message="create dev", root=str(git_repo))
        result = git(operation="checkout", message="dev", root=str(git_repo))
        assert result["status"] == "switched"
        assert result["to"] == "dev"

    def test_checkout_create_and_switch(self, git_repo):
        result = git(operation="checkout", message="-b new-feature", root=str(git_repo))
        assert result["status"] == "switched"
        assert result["branch"] == "new-feature"