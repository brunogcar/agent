"""
tests/workflows/understand/test_understand.py
Validates the Understand workflow structure and node logic.
"""
import pytest
from pathlib import Path
from workflows.understand import build_understand_graph, _default_state, node_init_project

def test_build_understand_graph_compiles():
    """Ensure the LangGraph state machine compiles without errors."""
    graph = build_understand_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")

def test_default_state_structure(tmp_path):
    """Ensure _default_state creates the correct initial structure."""
    project_path = tmp_path / "test_proj"
    project_path.mkdir()
    (project_path / "code").mkdir()  # Workspace projects need source root
    
    state = _default_state(str(project_path), is_agent_root=False)
    
    assert state["project_path"] == str(project_path.resolve())
    assert state["status"] == "running"
    assert state["files_to_parse"] == []
    assert state["files_parsed"] == 0

@pytest.mark.asyncio
async def test_node_init_project_creates_dirs(tmp_path):
    """Ensure node_init_project creates the .understand directory and kg.db."""
    project_path = tmp_path / "test_proj"
    project_path.mkdir()
    (project_path / "code").mkdir()  # Workspace projects need source root
    
    state = _default_state(str(project_path), is_agent_root=False)
    result = await node_init_project(state)
    
    assert result["status"] == "running"
    assert (project_path / ".understand").exists()
    assert (project_path / ".understand" / "kg.db").exists()