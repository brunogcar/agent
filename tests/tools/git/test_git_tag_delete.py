"""Tests for git tag_delete action."""
from tools.git import git


class TestTagDelete:
    """tag_delete removes a lightweight tag."""

    def test_tag_delete_success(self, git_repo):
        """Should delete tag and remove it from list."""
        git(action="tag_create", target="v0.9", root=str(git_repo))
        result = git(action="tag_delete", target="v0.9", root=str(git_repo))
        assert result["status"] == "deleted"
        assert result["tag"] == "v0.9"

        lst = git(action="tag_list", root=str(git_repo))
        assert "v0.9" not in lst["tags"]

    def test_tag_delete_missing_target(self, git_repo):
        """Missing target should return error."""
        result = git(action="tag_delete", root=str(git_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]
