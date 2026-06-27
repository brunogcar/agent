"""Shared fixtures for report tool tests.

All tests in this directory use tmp_path for workspace isolation.
No subprocess mocking — tests exercise actual report generation.
"""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch, tmp_path):
    """Redirect workspace_root and agent_root to tmp_path.

    Also bypasses path_guard by replacing resolve_path with a permissive version.
    This fixture runs automatically for every test in this directory.
    """
    monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
    monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)

    import pathlib
    def _fake_resolve(path, default_root="agent", require_exists=False):
        p = pathlib.Path(str(path))
        return (p, "")
    monkeypatch.setattr("core.path_guard.resolve_path", _fake_resolve)


@pytest.fixture
def report_dir(tmp_path):
    """Return the reports output directory for a trace_id.

    Usage: report_dir / "trace-123" / "report.html"
    """
    return tmp_path / "reports"
