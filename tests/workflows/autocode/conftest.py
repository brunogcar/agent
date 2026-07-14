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

    [v2.5+v2.6] Uses _default_state() to populate all 8 sub-states with
    defaults. The v2.0.5 split-brain bug (P1-1) was invisible to tests
    because tests built state without the sub-state — so the accessor
    fell through to the flat field and returned the correct value.
    _default_state() populates the sub-state with defaults, so accessors
    are exercised on the real code path. See Track M1 learning #2 in
    CHANGELOG.
    """
    from workflows.autocode_impl.state import _default_state
    state = _default_state(task="test task")
    # Override with the test-specific values that tests depend on:
    state["trace_id"] = "test-trace-001"
    state["task_type"] = "feature"
    state["project_root"] = str(temp_workspace)
    # plan: legacy list[dict] step list (tests read state["plan"] directly)
    state["plan"] = [{"id": 1, "label": "write_code", "description": "implement"}]
    state["current_step"] = 0
    state["test_files"] = []
    state["max_retries"] = 3
    return state
