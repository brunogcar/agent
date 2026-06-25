"""Test clone action.

These tests exercise the clone action with real git operations.
Clone is a WORKSPACE_ROOT-only operation - must use root="workspace".

Test operations target cfg.workspace_root / "tmp" to avoid polluting
the workspace root. The actual path is read from core.config.cfg at runtime,
respecting any .env overrides.
"""
from __future__ import annotations

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch
from tools.git import git
from core.config import cfg


class TestClone:
    def test_clone_missing_target(self):
        """clone without target (URL) should error."""
        test_workspace = cfg.workspace_root / "tmp"
        test_workspace.mkdir(parents=True, exist_ok=True)
        with patch("core.config.cfg.workspace_root", test_workspace):
            result = git(action="clone", root="workspace")
        assert result["status"] == "error"
        assert "target is required" in result["error"].lower()

    def test_clone_existing_directory_blocked(self):
        """clone into an existing directory should error."""
        test_workspace = cfg.workspace_root / "tmp"
        test_workspace.mkdir(parents=True, exist_ok=True)
        existing = test_workspace / "existing_repo"
        existing.mkdir(parents=True, exist_ok=True)

        try:
            with patch("core.config.cfg.workspace_root", test_workspace):
                result = git(
                    action="clone",
                    target="https://github.com/dummy/dummy.git",
                    path="existing_repo",
                    root="workspace",
                )
            assert result["status"] == "error"
            assert "already exists" in result["error"].lower()
        finally:
            import shutil
            shutil.rmtree(existing, ignore_errors=True)


class TestCloneRealIntegration:
    """Real clone tests using a local bare repo as the remote."""

    @pytest.fixture
    def bare_repo(self, tmp_path):
        """Create a local bare git repository to clone from.
        The bare repo itself lives in tmp_path (isolated), but clone targets go to
        cfg.workspace_root / "tmp" (read from .env at runtime).
        """
        bare = tmp_path / "remote.git"
        bare.mkdir()
        subprocess.run(
            ["git", "init", "--bare"],
            cwd=bare,
            check=True,
            capture_output=True,
        )
        return bare

    def test_clone_real_repo(self, bare_repo):
        """Clone a real bare repo into workspace/tmp."""
        test_workspace = cfg.workspace_root / "tmp"
        test_workspace.mkdir(parents=True, exist_ok=True)
        cloned = test_workspace / "cloned_repo"

        try:
            with patch("core.config.cfg.workspace_root", test_workspace):
                result = git(
                    action="clone",
                    target=str(bare_repo),
                    path="cloned_repo",
                    root="workspace",
                )
            assert result["status"] == "cloned"

            cloned_path = Path(result["path"])
            assert cloned_path.exists()
            assert (cloned_path / ".git").exists()
        finally:
            import shutil
            shutil.rmtree(cloned, ignore_errors=True)

    def test_clone_derives_name_from_url(self, bare_repo):
        """If path is not provided, derive name from URL."""
        test_workspace = cfg.workspace_root / "tmp"
        test_workspace.mkdir(parents=True, exist_ok=True)
        derived_name = "remote"  # "remote.git" -> "remote"
        cloned = test_workspace / derived_name

        try:
            with patch("core.config.cfg.workspace_root", test_workspace):
                result = git(
                    action="clone",
                    target=str(bare_repo),
                    root="workspace",
                )
            assert result["status"] == "cloned"
            assert derived_name in result["path"]

            cloned_path = Path(result["path"])
            assert cloned_path.exists()
            assert (cloned_path / ".git").exists()
        finally:
            import shutil
            shutil.rmtree(cloned, ignore_errors=True)
