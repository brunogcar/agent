"""tests/workflows/understand/test_state.py
Tests for UnderstandState and _default_state.
"""
from __future__ import annotations

from unittest.mock import patch

from workflows.understand_impl.state import _default_state


def test_default_state_structure(make_project):
    """_default_state creates the correct initial structure.

    [v1.4.1 P1-4] _default_state no longer instantiates ProjectManager.
    project_id + artifact_dir are empty strings until node_init_project
    fills them in.
    """
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False)
    assert state["project_path"] == str(project_path)  # NOT resolved — raw passthrough
    assert state["status"] == "running"
    assert state["files_to_parse"] == []
    assert state["files_parsed"] == 0
    assert state["edges_created"] == 0
    assert state["vectors_created"] == 0  # [#3]
    assert state["errors"] == []
    # [v1.4.1 P1-4] project_id + artifact_dir start as empty strings —
    # node_init_project fills them in via its partial dict.
    assert state["project_id"] == ""
    assert state["artifact_dir"] == ""


def test_default_state_includes_trace_id(make_project):
    """[Bug #2] _default_state must accept and inject trace_id."""
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False, trace_id="test-trace-123")
    assert state["trace_id"] == "test-trace-123"


def test_default_state_includes_skip_embeddings(make_project):
    """[v1.4.1 P2-5] _default_state must declare skip_embeddings (default False).

    Was: the field was on the TypedDict but missing from the returned dict,
    so callers that didn't explicitly set it relied on .get() defaulting.
    Now it's explicit.
    """
    project_path = make_project()
    state = _default_state(str(project_path), is_agent_root=False)
    assert "skip_embeddings" in state
    assert state["skip_embeddings"] is False


def test_default_state_does_not_instantiate_project_manager(make_project):
    """[v1.4.1 P1-4] _default_state must NOT instantiate ProjectManager.

    Was: `pm = ProjectManager(project_path, is_agent_root=is_agent_root)`
    at the top of _default_state — coupled state creation to kgraph
    availability. If PM init raised, the workflow couldn't even start.
    Now _default_state is pure defaults; init_project fills in PM-derived
    fields.

    Verified two ways:
      1. _default_state works even when ProjectManager is broken (patched
         to raise on instantiation).
      2. state.py source has no top-level ProjectManager import or
         instantiation.
    """
    from unittest.mock import patch as _patch

    project_path = make_project()

    # Patch ProjectManager.__init__ to raise — _default_state should NOT call it.
    # If it did, this would raise RuntimeError and the test would fail.
    with _patch.object(
        __import__("core.kgraph.project", fromlist=["ProjectManager"]).ProjectManager,
        "__init__",
        side_effect=RuntimeError("should not be called"),
    ):
        state = _default_state(str(project_path), is_agent_root=False)
        assert state["status"] == "running"
        assert state["project_id"] == ""

    # Stronger assertion: verify ProjectManager is NOT imported at module load
    # time of state.py (the import was removed in v1.4.1).
    import workflows.understand_impl.state as state_mod
    with open(state_mod.__file__, encoding="utf-8") as f:
        source = f.read()
    assert "from core.kgraph.project import ProjectManager" not in source, (
        "state.py must NOT import ProjectManager at module level (P1-4)"
    )
    assert "ProjectManager(" not in source, (
        "state.py must NOT instantiate ProjectManager in _default_state (P1-4)"
    )
