"""Tests for git branch_delete action."""
import subprocess
from tools.git import git


class TestBranchDelete:
    """branch_delete safely removes merged branches."""

    def test_branch_delete_success(self, git_repo):
        """Create branch, switch away, then delete it.

        Note: git init -b main forces default branch name.
        """
        git(action="branch_create", target="temp", root=str(git_repo))
        git(action="checkout_branch", target="temp", root=str(git_repo))
        # Switch back to default branch (main)
        git(action="checkout_branch", target="main", root=str(git_repo))

        result = git(action="branch_delete", target="temp", root=str(git_repo))
        assert result["status"] == "deleted"
        assert result["branch"] == "temp"

    def test_branch_delete_missing_target(self, git_repo):
        """Missing target should return error."""
        result = git(action="branch_delete", root=str(git_repo))
        assert result["status"] == "error"
        assert "target is required" in result["error"]

    def test_branch_delete_force_unmerged(self, git_repo):
        """Force delete an unmerged branch."""
        git(action="checkout_new", target="unmerged", root=str(git_repo))
        (git_repo / "new.txt").write_text("new", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "wip"], cwd=git_repo, check=True, capture_output=True)
        git(action="checkout_branch", target="main", root=str(git_repo))

        # Safe delete should fail (unmerged)
        result = git(action="branch_delete", target="unmerged", root=str(git_repo))
        assert result["status"] == "error"

        # Force delete should succeed
        result = git(action="branch_delete", target="unmerged", force=True, root=str(git_repo))
        assert result["status"] == "deleted"
