"""Tests for git branch_list action."""
import pytest
from tools.git import git


class TestBranchList:
    """branch_list returns all local branches with current marker."""

    def test_branch_list_returns_branches(self, git_repo):
        """Should return at least one branch (main/master) with current=True."""
        result = git(action="branch_list", root=str(git_repo))
        assert result["status"] == "success"
        assert len(result["branches"]) >= 1
        assert any(b["current"] for b in result["branches"])

    def test_branch_list_empty_repo(self, tmp_path):
        """Non-repo should return error from git itself."""
        result = git(action="branch_list", root=str(tmp_path))
        # git branch in non-repo returns error
        assert result["status"] == "error"
