"""Tests for git show action (target param rename from message)."""
from tools.git import git


class TestShow:
    """show displays commit/tag/tree details."""

    def test_show_head_default(self, git_repo):
        """Default target should show HEAD."""
        result = git(action="show", root=str(git_repo))
        assert result["status"] == "success"
        assert "initial" in result["output"]

    def test_show_specific_commit(self, git_repo):
        """Should show a specific commit by hash."""
        log = git(action="log", n=1, root=str(git_repo))
        head_hash = log["commits"][0]["hash"]
        result = git(action="show", target=head_hash, root=str(git_repo))
        assert result["status"] == "success"

    def test_show_tag(self, git_repo):
        """Should show a tag."""
        git(action="tag_create", target="v1.0", root=str(git_repo))
        result = git(action="show", target="v1.0", root=str(git_repo))
        assert result["status"] == "success"
