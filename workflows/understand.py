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

[v1.5] Re-exports `query_codebase` + `health_check` from
`workflows.understand_query` so callers that already import from this
facade get the new query/health entry points without an extra import.
The `action` parameter on `run_workflow(type='understand')` (in base.py)
routes to these — but they're also available directly:

    from workflows.understand import query_codebase, health_check

[v1.5] `run_understand_workflow_sync` now accepts an `action` parameter
(default "index") so standalone callers can route to query/health without
going through base.py's run_workflow() dispatcher. The action routing
mirrors base.py's understand branch: action="query" → query_codebase(),
action="health" → health_check(), action="index" → graph.invoke().
Backward compatible — existing callers that don't pass action get the
index behavior.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from workflows.understand_impl.graph import build_understand_graph, WORKFLOW_METADATA
from workflows.understand_impl.state import _default_state, UnderstandState
from workflows.understand_query import query_codebase, health_check
from core.tracer import tracer
from core.config import cfg


def run_understand_workflow_sync(
    project_path: str,
    is_agent_root: bool = False,
    trace_id: str = "",
    action: str = "index",
    question: str = "",
    query_type: str = "semantic",
    file_path: str = "",
    top_k: int = 10,
    **_extra: Any,
) -> dict:
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

    [v1.5] `action` parameter routes BEFORE graph construction:
      - action="index"  (default) → run the full LangGraph (backward compat).
      - action="query"  → call query_codebase() directly (no graph).
      - action="health" → call health_check() directly (no graph).
    For action="query", pass `question` (the search query), `query_type`
    (semantic/keyword/dependencies/callers), `file_path` (for deps/callers),
    and `top_k` (max results). For action="health", no extra params needed.
    Unknown action → clean failure dict.
    """
    # [v1.5] Route by action BEFORE trace creation — query/health have
    # their own trace creation in understand_query.py with action-specific
    # goal strings. For action="index", we create the trace here (unchanged).
    if action == "query":
        # Validate project_path exists (consistent with the index path).
        if not project_path or not Path(project_path).exists():
            msg = f"Project path does not exist: {project_path}"
            tracer.error(trace_id or "understand", "understand", msg)
            return {"status": "failed", "errors": [msg]}
        # Lazy import is_same_path to detect agent_root (mirrors index path).
        from core.kgraph.project import is_same_path
        is_agent = is_same_path(project_path, cfg.agent_root) if project_path else False
        return query_codebase(
            project_path=project_path,
            question=question,
            query_type=query_type,
            file_path=file_path,
            top_k=top_k,
            is_agent_root=is_agent or is_agent_root,
            trace_id=trace_id,
        )

    if action == "health":
        if not project_path or not Path(project_path).exists():
            msg = f"Project path does not exist: {project_path}"
            tracer.error(trace_id or "understand", "understand", msg)
            return {"status": "failed", "errors": [msg]}
        from core.kgraph.project import is_same_path
        is_agent = is_same_path(project_path, cfg.agent_root) if project_path else False
        return health_check(
            project_path=project_path,
            is_agent_root=is_agent or is_agent_root,
            trace_id=trace_id,
        )

    if action != "index":
        msg = f"Unknown action: {action}. Use: index (default), query, health"
        tracer.error(trace_id or "understand", "understand", msg)
        return {"status": "failed", "errors": [msg]}

    # ─── action="index" (default) — original graph.invoke() path ────────
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
    # [v1.5] Query interface + health check (re-exported from
    # workflows.understand_query). Surface here for callers that already
    # import from this facade.
    "query_codebase",
    "health_check",
]
