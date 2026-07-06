"""workflows/understand.py — Thin facade for the understand workflow.

[Decision] v1.0: Split from monolithic file into understand_impl/ subpackage.
All node logic lives in workflows/understand_impl/nodes/.
Graph builder and metadata in workflows/understand_impl/graph.py.
State definitions in workflows/understand_impl/state.py.

[Decision] run_understand_workflow_sync() is kept here for backward compat
as a standalone entry point. base.py does NOT use it — base.py imports
build_understand_graph() and _default_state() directly and calls
graph.invoke() itself.
"""
from __future__ import annotations

from workflows.understand_impl.graph import build_understand_graph, WORKFLOW_METADATA
from workflows.understand_impl.state import _default_state, UnderstandState
from core.tracer import tracer
from core.config import cfg
from core.kgraph.project import is_same_path


def run_understand_workflow_sync(project_path: str, is_agent_root: bool = False, trace_id: str = "") -> dict:
    """Synchronous entry point for the understand workflow.

    [Decision] Kept for backward compat — base.py doesn't use this.
    Standalone callers can use it to run understand without going through
    base.py's run_workflow() dispatcher.

    Treats both "completed" and "completed_with_errors" as success.
    """
    tid = trace_id or tracer.new_trace("understand", goal=f"Index codebase at {project_path}")
    try:
        if is_same_path(project_path, cfg.agent_root):
            is_agent_root = True

        graph = build_understand_graph()
        initial_state = _default_state(project_path, is_agent_root=is_agent_root, trace_id=tid)
        final_state = graph.invoke(initial_state)

        success = final_state.get("status", "") in ("completed", "completed_with_errors")
        tracer.finish(tid, success=success, result=str(final_state))
        return final_state
    except Exception as e:
        tracer.error(tid, "understand", f"Workflow failed: {e}")
        tracer.finish(tid, success=False, result=str(e))
        return {"status": "failed", "errors": [str(e)]}


__all__ = [
    "build_understand_graph",
    "WORKFLOW_METADATA",
    "_default_state",
    "UnderstandState",
    "run_understand_workflow_sync",
]
