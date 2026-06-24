"""Tests for git tag_list action."""
from tools.git import git


class TestTagList:
    """tag_list returns all lightweight tags."""

    def test_tag_list_empty(self, git_repo):
        """New repo should have no tags."""
        result = git(action="tag_list", root=str(git_repo))
        assert result["status"] == "success"
        assert result["tags"] == []

    def test_tag_list_with_tags(self, git_repo):
        """After creating tags, they should appear in list."""
        git(action="tag_create", target="v1.0", root=str(git_repo))
        git(action="tag_create", target="v2.0", root=str(git_repo))

        result = git(action="tag_list", root=str(git_repo))
        assert result["status"] == "success"
        assert "v1.0" in result["tags"]
        assert "v2.0" in result["tags"]
