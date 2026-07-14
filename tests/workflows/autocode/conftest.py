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

    [v3.0] Uses _default_state() — sub-states are now the PRIMARY (and only)
    storage for the grouped fields. The v2.x split-brain pattern (test
    writes to BOTH sub-state + flat field) is gone — flat mirror fields
    no longer exist in _default_state(). Tests must write to the sub-state
    directly when they want to override a sub-state field.
    """
    from workflows.autocode_impl.state import _default_state
    state = _default_state(task="test task")
    # Override with the test-specific values that tests depend on:
    state["trace_id"] = "test-trace-001"
    state["task_type"] = "feature"
    state["project_root"] = str(temp_workspace)
    # plan: list[dict] step list lives ONLY in the plan sub-state (post-v3.0).
    test_plan = [{"id": 1, "label": "write_code", "description": "implement"}]
    state["plan_state"]["plan"] = test_plan
    state["plan_state"]["current_step"] = 0
    state["test_files"] = []
    # max_retries lives ONLY in the tdd sub-state (post-v3.0).
    state["tdd"]["max_retries"] = 3
    return state
