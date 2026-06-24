"""Tests for git checkout_branch action."""
from tools.git import git


class TestCheckoutBranch:
    """checkout_branch switches to an existing branch."""

    def test_checkout_branch_success(self, git_repo):
        """Create branch, then switch to it.

        Note: git init default branch is 'master'.
        """
        git(action="branch_create", target="dev", root=str(git_repo))
        result = git(action="checkout_branch", target="dev", root=str(git_repo))
        assert result["status"] == "switched"
        assert result["to"] == "dev"

    def test_checkout_branch_missing_target(self, git_repo):
        """Missing target should return error."""
        result = git(action="checkout_branch", root=str(git_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]
