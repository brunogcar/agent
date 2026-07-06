"""tests/workflows/understand/test_init_project.py
Tests for node_init_project.
"""
from __future__ import annotations

from workflows.understand_impl.state import _default_state
from workflows.understand_impl.nodes.init_project import node_init_project


def test_node_init_project_creates_dirs(make_project):
    """node_init_project creates the .understand directory and kg.db."""
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False, trace_id="test")
    result = node_init_project(state)
    assert result["status"] == "running"
    assert (project_path / ".understand").exists()
    assert (project_path / ".understand" / "kg.db").exists()


def test_node_init_project_fails_without_code_dir(tmp_path):
    """Workspace projects without code/ directory must fail with clear error."""
    project_path = tmp_path / "bad_proj"
    project_path.mkdir()
    state = _default_state(str(project_path), is_agent_root=False, trace_id="test")
    result = node_init_project(state)
    assert result.get("status") == "failed"
    assert "errors" in result
