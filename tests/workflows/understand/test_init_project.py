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


def test_node_init_project_returns_project_id_and_artifact_dir(make_project):
    """[v1.4.1 P1-4] node_init_project must fill in project_id + artifact_dir.

    _default_state no longer instantiates ProjectManager — these fields
    start as empty strings and are populated by init_project's partial dict.
    """
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False, trace_id="test")
    # Sanity: they start empty.
    assert state["project_id"] == ""
    assert state["artifact_dir"] == ""

    result = node_init_project(state)
    assert result["status"] == "running"
    assert result["project_id"] != "", "init_project must return a non-empty project_id"
    assert result["artifact_dir"] != "", "init_project must return a non-empty artifact_dir"
    # artifact_dir should point at {project}/.understand/
    assert ".understand" in result["artifact_dir"]
    # project_id is a 16-char hex string (sha256[:16] of the resolved path).
    assert len(result["project_id"]) == 16
    assert all(c in "0123456789abcdef" for c in result["project_id"])


def test_node_init_project_normalizes_project_path(make_project):
    """[v1.4.1 P1-4] init_project normalizes project_path to resolved form.

    _default_state stores the raw input string; init_project runs it
    through ProjectManager.__init__ which calls .resolve() and overwrites
    the field with the normalized form.
    """
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False, trace_id="test")
    result = node_init_project(state)
    assert result["project_path"] == str(project_path.resolve())
