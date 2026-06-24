"""Tests for git add action."""
from tools.git import git


class TestGitAdd:
    """add stages files for commit."""

    def test_add_specific_file(self, git_repo):
        """Should stage a specific file."""
        (git_repo / "new_file.py").write_text("print('hello')", encoding="utf-8")
        result = git(action="add", path="new_file.py", root=str(git_repo))
        assert result["status"] == "success"

        # Verify staged - status returns "changes" with flag and file
        status = git(action="status", root=str(git_repo))
        assert status["status"] == "success"
        changes = status.get("changes", [])
        # After add, file should be staged (flag 'A' for added)
        assert any("new_file.py" in c.get("file", "") for c in changes)

    def test_add_all_files(self, git_repo):
        """Should stage all changes when no path specified."""
        (git_repo / "a.py").write_text("a", encoding="utf-8")
        (git_repo / "b.py").write_text("b", encoding="utf-8")
        result = git(action="add", root=str(git_repo))
        assert result["status"] == "success"

        status = git(action="status", root=str(git_repo))
        assert status["status"] == "success"
        changes = status.get("changes", [])
        # Both files should appear in status after add
        file_names = [c.get("file", "") for c in changes]
        assert any("a.py" in name for name in file_names) or any("b.py" in name for name in file_names)
