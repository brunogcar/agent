"""Node: init_project — Initialize the project for indexing.

[v1.4.1 P1-4] Now returns `project_id` + `artifact_dir` in its partial dict.
Was: those fields were set by `_default_state()` (which instantiated
ProjectManager eagerly at state-creation time — coupling state creation to
kgraph availability). Now `_default_state()` returns pure defaults (empty
strings for project_id + artifact_dir) and this node fills them in.

[v1.4.1 P1-7] GraphStore creation already inside try (was already correct
in v1.3.1, but we add a comment to make the pattern explicit for future
contributors — see discover_files.py and parse_and_store.py for the same
pattern).
"""
from __future__ import annotations

from workflows.understand_impl.state import UnderstandState
from core.tracer import tracer
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore


def node_init_project(state: UnderstandState) -> dict:
    """Initialize the project for indexing.

    [v1.4.1 P1-4] Returns project_id + artifact_dir in the partial dict so
    downstream nodes (discover_files, parse_and_store) don't need to
    re-instantiate ProjectManager just to get them. (They DO re-instantiate
    PM for other reasons — path resolution, MAX_FILE_SIZE_BYTES, etc. —
    but having project_id in state avoids one redundant call.)
    """
    tid = state.get("trace_id", "understand")
    tracer.step(tid, "init", f"Initializing project {state['project_path']}")

    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])

    if not pm.is_agent_root and not pm.source_root.exists():
        return {"status": "failed", "errors": [f"Source root does not exist: {pm.source_root}. Did the git clone fail?"]}

    mode = pm.get_indexing_mode()
    if mode == "reject":
        return {"status": "failed", "errors": ["Project too large for indexing."]}

    pm.ensure_initialized()

    db_path = pm.artifact_root / "kg.db"
    # [v1.4.1 P1-7] GraphStore created inside try (was already correct here,
    # but the comment makes the pattern explicit — see discover_files.py
    # and parse_and_store.py for the version that was actually broken).
    try:
        store = GraphStore(db_path)
        store.close()
    except Exception as e:
        return {"status": "failed", "errors": [f"GraphStore init failed: {e}"]}

    # [v1.4.1 P1-4] Return project_id + artifact_dir so downstream nodes
    # have them without re-instantiating PM just for these fields.
    return {
        "status": "running",
        "project_id": pm.project_id,
        "artifact_dir": str(pm.artifact_root),
        "project_path": str(pm.path),  # normalize to resolved form
    }
