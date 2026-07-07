"""State definitions and defaults for the understand workflow.

[Decision] Uses a separate UnderstandState TypedDict (not WorkflowState from base.py)
because understand has unique fields: project_path, is_agent_root, project_id,
artifact_dir, files_to_parse, files_parsed, edges_created. These don't exist
in the shared WorkflowState.
"""
from __future__ import annotations

from typing import TypedDict, Any
from core.kgraph.project import ProjectManager


class UnderstandState(TypedDict, total=False):
    project_path: str
    is_agent_root: bool
    project_id: str
    artifact_dir: str
    trace_id: str
    status: str
    files_to_parse: list[tuple[str, str, str, float, int]]
    files_parsed: int
    edges_created: int
    vectors_created: int  # [#3] code embeddings stored in ChromaDB
    errors: list[str]


def _default_state(project_path: str, is_agent_root: bool = False, trace_id: str = "") -> UnderstandState:
    """Create initial state for the understand workflow."""
    pm = ProjectManager(project_path, is_agent_root=is_agent_root)
    return {
        "project_path": str(pm.path),
        "is_agent_root": is_agent_root,
        "project_id": pm.project_id,
        "artifact_dir": str(pm.artifact_root),
        "trace_id": trace_id,
        "status": "running",
        "files_to_parse": [],
        "files_parsed": 0,
        "edges_created": 0,
        "vectors_created": 0,
        "errors": [],
    }
