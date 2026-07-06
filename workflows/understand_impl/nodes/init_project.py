"""Node: init_project — Initialize the project for indexing."""
from __future__ import annotations

from workflows.understand_impl.state import UnderstandState
from core.tracer import tracer
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore


def node_init_project(state: UnderstandState) -> dict:
    """Initialize the project for indexing."""
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
    try:
        store = GraphStore(db_path)
        store.close()
    except Exception as e:
        return {"status": "failed", "errors": [f"GraphStore init failed: {e}"]}

    return {"status": "running"}
