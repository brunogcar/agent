"""Shared fixtures for git tool tests.

All tests in this directory use real git repositories in tmp_path.
No subprocess mocking — tests exercise actual git operations.
"""
from __future__ import annotations

import subprocess
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch, tmp_path):
    """Redirect agent_root and workspace_root to tmp_path.

    Also bypasses path_guard by replacing resolve_path with a permissive version.
    This fixture runs automatically for every test in this directory.
    """
    monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)
    monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)

    import pathlib
    def _fake_resolve(path, default_root="agent", require_exists=False):
        p = pathlib.Path(str(path))
        return (p, "")
    monkeypatch.setattr("core.path_guard.resolve_path", _fake_resolve)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit.

    Returns the Path to the repo directory. The repo has:
    - git config for user.email and user.name
    - One file (file.txt) with "initial content"
    - One commit with message "initial"
    - Default branch forced to "main" (independent of git config)
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    # Force branch name to "main" for test determinism
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@agent.local"],
        cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Agent"],
        cwd=repo, check=True, capture_output=True
    )
    (repo / "file.txt").write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo, check=True, capture_output=True
    )
    return repo
