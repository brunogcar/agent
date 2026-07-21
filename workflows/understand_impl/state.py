"""State definitions and defaults for the understand workflow.

[Decision] Uses a separate UnderstandState TypedDict (not WorkflowState from base.py)
because understand has unique fields: project_path, is_agent_root, project_id,
artifact_dir, files_to_parse, files_parsed, edges_created. These don't exist
in the shared WorkflowState.

[v1.4.1 P1-4] _default_state() no longer instantiates ProjectManager. The PM
was being created eagerly at state-construction time, which coupled state
creation to kgraph availability — if PM init raised (kgraph import failure,
disk full, etc.), the entire workflow couldn't even start. Now _default_state
returns pure defaults; project_id + artifact_dir are filled in by
node_init_project (which has its own try/except + tracer logging).

[v1.4.1 P2-5] skip_embeddings is now declared in _default_state (was: only
on the TypedDict; the field was missing from the returned dict, so callers
that didn't explicitly set it relied on .get() defaulting to False).

[v1.4.1 P2-6] `note: str` field added to UnderstandState. node_parse_and_store
already sets it (the "No changed files — codebase is up to date." message)
and node_report already reads it via state.get("note", "") — but the field
wasn't declared on the TypedDict, so the contract was implicit. Now it's
explicit + type-safe.
"""
from __future__ import annotations

from typing import TypedDict


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
    skip_embeddings: bool  # v1.4: skip vector indexing (graph-only mode)
    note: str  # v1.4.1 P2-6: human-readable note surfaced by node_report (e.g. "up to date")


def _default_state(project_path: str, is_agent_root: bool = False, trace_id: str = "") -> UnderstandState:
    """Create initial state for the understand workflow.

    [v1.4.1 P1-4] Pure defaults only — no ProjectManager instantiation.
    `project_path` is stored verbatim (the caller passes whatever they have;
    node_init_project will call Path(project_path).resolve() via ProjectManager
    and overwrite this field with the resolved form). `project_id` and
    `artifact_dir` are left as empty strings; node_init_project fills them in
    when it constructs its own ProjectManager. This decouples state creation
    from kgraph availability — if ProjectManager init would raise, the workflow
    can still START, hit init_project, and produce a clean failure dict
    instead of crashing during _default_state.
    """
    return {
        "project_path": str(project_path),
        "is_agent_root": is_agent_root,
        # Filled in by node_init_project (returns them in its partial dict).
        "project_id": "",
        "artifact_dir": "",
        "trace_id": trace_id,
        "status": "running",
        "files_to_parse": [],
        "files_parsed": 0,
        "edges_created": 0,
        "vectors_created": 0,
        "errors": [],
        # [v1.4.1 P2-5] explicit default — was: implicit via .get(skip_embeddings, False)
        "skip_embeddings": False,
    }
