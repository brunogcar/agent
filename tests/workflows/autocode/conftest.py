"""Shared fixtures for autocode workflow tests.

All fixtures patch cfg.workspace_root / cfg.agent_root to tmp_path so
no test ever touches the real project. LLM, git, and memory calls are
mocked per-test.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """Patch cfg.workspace_root + cfg.agent_root to tmp_path for safe file writes."""
    import core.config
    monkeypatch.setattr(core.config.cfg, "workspace_root", tmp_path)
    monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)
    yield tmp_path


@pytest.fixture
def base_state(temp_workspace):
    """Minimal valid AutocodeState for node tests.

    Tests override only the fields they need. dry_run defaults to False
    so mutation nodes actually run; tests that want dry-run set it True.
    """
    return {
        "task": "test task",
        "trace_id": "test-trace-001",
        "status": "running",
        "dry_run": False,
        "task_type": "feature",
        "project_root": str(temp_workspace),
        "plan": [{"id": 1, "label": "write_code", "description": "implement"}],
        "current_step": 0,
        "tdd_iteration": 0,
        "tdd_status": "",
        "tdd_source_code": "",
        "tdd_error": "",
        "last_test_error": "",
        "test_results": {},
        "test_files": [],
        "verification_passed": False,
        "modified_files": [],
        "files_map": {},
        "max_retries": 3,
        "messages": [],
        "error": "",
        "result": "",
    }
