"""Tests for git checkout_new action."""
from tools.git import git


class TestCheckoutNew:
    """checkout_new creates and switches to a new branch."""

    def test_checkout_new_success(self, git_repo):
        """Should create branch and switch to it in one step."""
        result = git(action="checkout_new", target="feature-x", root=str(git_repo))
        assert result["status"] == "switched"
        assert result["branch"] == "feature-x"

        # Verify current branch
        lst = git(action="branch_list", root=str(git_repo))
        current = [b["name"] for b in lst["branches"] if b["current"]]
        assert "feature-x" in current

    def test_checkout_new_missing_target(self, git_repo):
        """Missing target should return error."""
        result = git(action="checkout_new", root=str(git_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]
