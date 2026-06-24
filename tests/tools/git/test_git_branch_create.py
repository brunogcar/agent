"""Tests for git branch_create action."""
import pytest
from tools.git import git


class TestBranchCreate:
    """branch_create creates a new branch pointer at current HEAD."""

    def test_branch_create_success(self, git_repo):
        """Should create branch and return it in branch_list."""
        result = git(action="branch_create", target="feature-x", root=str(git_repo))
        assert result["status"] == "created"
        assert result["branch"] == "feature-x"

        # Verify it exists
        lst = git(action="branch_list", root=str(git_repo))
        names = [b["name"] for b in lst["branches"]]
        assert "feature-x" in names

    def test_branch_create_missing_target(self, git_repo):
        """Missing target should return error."""
        result = git(action="branch_create", root=str(git_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]

    def test_branch_create_duplicate(self, git_repo):
        """Creating duplicate branch should fail."""
        git(action="branch_create", target="dup", root=str(git_repo))
        result = git(action="branch_create", target="dup", root=str(git_repo))
        assert result["status"] == "error"
