"""Shared fixtures for all CLI tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import os as _os


@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch):
    """Mock cfg for ALL tests in this directory to prevent AsyncMock leakage."""
    mock = MagicMock()
    mock.cli_max_command_chars = 4096
    mock.cli_max_arguments = 50
    # Use a real Path for workspace_root so path resolution works
    mock.workspace_root = Path(_os.getcwd())
    mock.agent_root = Path(_os.getcwd()).parent  # or appropriate

    # Patch at the source: core.config.cfg
    # This ensures ALL imports (tools.cli, tools.cli_ops.helpers, etc.) get the same mock
    monkeypatch.setattr("core.config.cfg", mock)
    return mock


@pytest.fixture(autouse=True)
def reset_dispatch():
    """Reset DISPATCH registry between tests to prevent action leakage."""
    from tools.cli_ops._registry import DISPATCH
    original = {k: dict(v) for k, v in DISPATCH.items()}
    yield
    DISPATCH.clear()
    DISPATCH.update(original)
