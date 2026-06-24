"""Tests for git tag_create action."""
from tools.git import git


class TestTagCreate:
    """tag_create creates a lightweight tag at current HEAD."""

    def test_tag_create_success(self, git_repo):
        """Should create tag and return it."""
        result = git(action="tag_create", target="v1.0", root=str(git_repo))
        assert result["status"] == "created"
        assert result["tag"] == "v1.0"

    def test_tag_create_missing_target(self, git_repo):
        """Missing target should return error."""
        result = git(action="tag_create", root=str(git_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]
