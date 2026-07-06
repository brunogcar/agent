"""tests/workflows/understand/test_state.py
Tests for UnderstandState and _default_state.
"""
from __future__ import annotations

from workflows.understand_impl.state import _default_state


def test_default_state_structure(make_project):
    """_default_state creates the correct initial structure."""
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False)
    assert state["project_path"] == str(project_path.resolve())
    assert state["status"] == "running"
    assert state["files_to_parse"] == []
    assert state["files_parsed"] == 0


def test_default_state_includes_trace_id(make_project):
    """[Bug #2] _default_state must accept and inject trace_id."""
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False, trace_id="test-trace-123")
    assert state["trace_id"] == "test-trace-123"
