"""Integration tests for git tool dispatch routing."""
import subprocess
import pytest
from tools.git import git


@pytest.fixture(autouse=True)
def _use_temp_roots(monkeypatch, tmp_path):
    """Redirect agent_root and workspace_root to tmp_path (a real Path object) so path guard allows tests."""
    monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)
    monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
    """Bypass path guard by replacing resolve_path with a permissive version."""
    import pathlib
    def _fake_resolve(path, default_root="agent", require_exists=False):
        p = pathlib.Path(str(path))
        return (p, "")
    monkeypatch.setattr("core.path_guard.resolve_path", _fake_resolve)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True)
    return repo


class TestGitDispatch:
    def test_status_dispatch(self, git_repo):
        """Verify dispatcher routes to status and returns expected schema."""
        result = git(operation="status", root=str(git_repo))
        assert result.get("status") == "ok"
        assert "head" in result
        assert "changes" in result
        assert result.get("root") == str(git_repo)

    def test_unknown_action(self):
        """Verify dispatcher rejects unregistered operations."""
        result = git(operation="nonexistent_op")
        assert result.get("status") == "error"
        assert "Unknown action" in result.get("error", "")