"""workflows/understand.py — Thin facade for the understand workflow.

[Decision] v1.0: Split from monolithic file into understand_impl/ subpackage.
All node logic lives in workflows/understand_impl/nodes/.
Graph builder and metadata in workflows/understand_impl/graph.py.
State definitions in workflows/understand_impl/state.py.

[Decision] run_understand_workflow_sync() is kept here for backward compat
as a standalone entry point. base.py does NOT use it — base.py imports
build_understand_graph() and _default_state() directly and calls
graph.invoke() itself.

[v1.4.1 P0-2] `is_same_path` import moved INSIDE run_understand_workflow_sync.
Was: top-level `from core.kgraph.project import is_same_path`. If kgraph
had ANY import-time failure (broken tree_sitter_languages install, missing
chromadb, syntax error in any kgraph module), the entire `workflows.understand`
module failed to import → cascaded to `workflows/base.py` (which imports
understand lazily inside its dispatch branch, so base.py itself was OK) →
but any caller that did `from workflows.understand import ...` got an
ImportError. Now the import is deferred to call time — base.py's
understand branch also lazy-imports is_same_path (already did before
v1.4.1), so the cascade is fully broken.

[v1.4.1 P2-7] Success path now normalizes the return shape to always
include `errors: []` (was: only the error path included it). Callers can
now rely on `result["errors"]` always being a list.

[v1.4.1 P2-9] Validates project_path at entry — returns a clean failure
dict for a non-existent path instead of letting ProjectManager raise
inside node_init_project (which would now be caught by route_after_init,
but returning earlier is cleaner + avoids the cost of constructing the
graph).
"""
from __future__ import annotations

from pathlib import Path

from workflows.understand_impl.graph import build_understand_graph, WORKFLOW_METADATA
from workflows.understand_impl.state import _default_state, UnderstandState
from core.tracer import tracer
from core.config import cfg


def run_understand_workflow_sync(project_path: str, is_agent_root: bool = False, trace_id: str = "") -> dict:
    """Synchronous entry point for the understand workflow.

    [Decision] Kept for backward compat — base.py doesn't use this.
    Standalone callers can use it to run understand without going through
    base.py's run_workflow() dispatcher.

    Treats both "completed" and "completed_with_errors" as success.

    [v1.4.1 P2-7] Always returns a dict with `status` and `errors` keys.
    Success path ensures `errors` is present (defaults to []) so callers
    don't need to .get("errors", []) defensively.

    [v1.4.1 P2-9] Returns a clean failure dict for a non-existent
    project_path. Was: ProjectManager(project_path) would resolve() the
    path (no error) → node_init_project would fail inside is_agent_root
    branch (source_root == path doesn't exist) or workspace branch
    (path/code doesn't exist). Now fails fast at the facade.
    """
    tid = trace_id or tracer.new_trace("understand", goal=f"Index codebase at {project_path}")
    try:
        # [v1.4.1 P2-9] Validate project_path exists before building the graph.
        # ProjectManager.__init__ does Path(project_path).resolve() which never
        # raises on its own — the failure surfaces later inside node_init_project.
        # Returning early here is cheaper + gives a clearer error message.
        if not project_path or not Path(project_path).exists():
            msg = f"Project path does not exist: {project_path}"
            tracer.error(tid, "understand", msg)
            tracer.finish(tid, success=False, result=msg)
            return {"status": "failed", "errors": [msg]}

        # [v1.4.1 P0-2] Lazy import — keeps `workflows.understand` importable
        # even if `core.kgraph.project` is broken at import time.
        from core.kgraph.project import is_same_path

        if is_same_path(project_path, cfg.agent_root):
            is_agent_root = True

        graph = build_understand_graph()
        initial_state = _default_state(project_path, is_agent_root=is_agent_root, trace_id=tid)
        final_state = graph.invoke(initial_state)

        # [v1.4.1 P2-7] Normalize the return shape — error path always had
        # `errors`, success path didn't. Now both do.
        if "errors" not in final_state:
            final_state["errors"] = []

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
