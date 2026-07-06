"""Shared fixtures for understand workflow tests."""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def make_project(tmp_path):
    """Create a test project with code/ directory."""
    def _make(name="test_proj"):
        project_path = tmp_path / name
        project_path.mkdir()
        (project_path / "code").mkdir()
        return project_path
    return _make
