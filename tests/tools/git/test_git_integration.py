"""Integration tests for git tool dispatch routing."""
import subprocess
import pytest
from tools.git import git


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@agent.local"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "readme.md").write_text("# Test Repo", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestGitDispatch:
    def test_status_dispatch(self, git_repo):
        """Verify dispatcher routes to status and returns expected schema."""
        result = git(operation="status", root=str(git_repo))
        assert result.get("status") == "ok"
        assert "head" in result
        assert "changes" in result
        assert result.get("root") == str(git_repo)

    def test_unknown_operation(self):
        """Verify dispatcher rejects unregistered operations."""
        result = git(operation="nonexistent_op")
        assert result.get("status") == "error"
        assert "Unknown operation" in result.get("error", "")