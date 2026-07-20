"""tools/workflow_ops/helpers.py — Shared utilities for workflow actions and types.

Extracted from the original 263-line tools/workflow.py during the v1.0
@meta_tool refactor. These helpers are pure functions (with controlled side
effects: tracer calls, run_workflow invocations), so they can be unit-tested
in isolation.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. _make_error() is the SINGLE error response builder for the workflow
     tool. It guarantees every error includes a trace_id. NEVER replace it
     with fail() — the workflow tool's error format with trace_id is
     different from fail()'s format. Every error returns:
         {"status": "error", "error": <msg>, "trace_id": <id>, **extra}
  2. _ensure_trace_id() generates a new trace_id if the caller didn't
     provide one. It is called by EVERY type handler so that early
     validation failures are still logged with a trace_id.
  3. _validate_goal() returns bool (not tuple). It logs to tracer when
     validation fails — callers still need to call _make_error() to build
     the response dict.
  4. _execute_workflow() is the SINGLE entry point to workflows.base.run_workflow.
     It builds kwargs conditionally based on workflow type, calls
     run_workflow, and ensures trace_id is in the returned dict. This
     centralizes the kwargs-building logic that was previously inlined in
     the facade.
  5. _get_all_workflow_metadata() lazily imports each workflow module's
     graph.py and reads WORKFLOW_METADATA. Imports are wrapped in
     try/except so a broken module doesn't break the entire list action —
     it shows up as an "error" entry instead.

[WHY NOT fail()]:
  The workflow tool's error contract requires trace_id on EVERY response,
  including errors from early validation. fail() from registry.py doesn't
  include trace_id. The workflow tool also returns status="error" (not
  "failed") for backwards compat with the existing JSONL log analyzers.

[v1.1-p1] timeout passthrough:
  _execute_workflow() reads `timeout` from **kwargs (default 0) and forwards
  it to run_workflow(). Type handlers don't need to special-case timeout —
  it flows through **kwargs. For autocode, run_workflow ignores the timeout
  param (autocode manages its own via invoke_with_timeout).
"""
from __future__ import annotations

import importlib
from typing import Any, Dict

from core.tracer import tracer


# ── Error builder ────────────────────────────────────────────────────────────
def _make_error(error: str, trace_id: str, **extra) -> dict:
    """Build a standardized error response with trace_id.

    Centralizing error formatting guarantees that JSONL logs can always
    correlate workflow failures back to the original request — even for
    failures that occur before run_workflow() is called (validation,
    auto-routing, etc.).

    Args:
        error: Human-readable error message.
        trace_id: Observability threading ID. May be "" if the failure
                  occurred before _ensure_trace_id() ran — but in practice
                  every call path through a type handler ensures a trace_id
                  first.
        **extra: Additional fields to include in the response (e.g.
                 workflow_type, mode, valid_types).

    Returns:
        Dict with status="error", error, trace_id, and any extra fields.
    """
    result: Dict[str, Any] = {
        "status": "error",
        "error": error,
        "trace_id": trace_id,
    }
    result.update(extra)
    return result


# ── Trace ID management ──────────────────────────────────────────────────────
def _ensure_trace_id(trace_id: str, goal: str) -> str:
    """Return trace_id if non-empty, else generate a new one via tracer.

    Every workflow run needs a trace_id for JSONL log correlation. If the
    MCP host doesn't pass one, this generates one immediately so even
    early validation failures are logged correctly.

    Args:
        trace_id: Caller-supplied trace ID (may be "").
        goal: Goal text — used as the trace metadata.

    Returns:
        A non-empty trace_id string.
    """
    if trace_id:
        return trace_id
    return tracer.new_trace("workflow", goal=goal)


# ── Goal validation ──────────────────────────────────────────────────────────
def _validate_goal(goal: str, trace_id: str = "") -> bool:
    """Check that goal is non-empty after stripping whitespace.

    Args:
        goal: The workflow goal string.
        trace_id: Used for logging the validation failure.

    Returns:
        True if goal is non-empty, False otherwise. When False, the
        failure is logged to the tracer.
    """
    if goal and goal.strip():
        return True
    tracer.error(trace_id, "workflow", "Missing goal parameter")
    return False


# ── Workflow execution ───────────────────────────────────────────────────────
def _execute_workflow(
    wf_type: str,
    goal: str,
    trace_id: str,
    resume: bool = False,
    timeout: int = 0,
    **kwargs: Any,
) -> dict:
    """Invoke workflows.base.run_workflow with the correct kwargs per type.

    This is the SINGLE entry point for workflow execution — extracted from
    the old facade's inline if/elif chain. Each type handler calls this
    with the kwargs it has assembled.

    Args:
        wf_type: Workflow type ("research", "data", "autocode", etc.).
        goal: Goal text — always passed to run_workflow.
        trace_id: Observability threading ID — always passed.
        resume: Whether to resume from checkpoint.
        timeout: Per-workflow timeout in seconds (0 = no timeout). For
                 autocode, this is ignored — autocode uses
                 cfg.autocode_graph_timeout + invoke_with_timeout. For
                 other workflows, wraps graph.invoke() with a daemon-thread
                 deadline.
        **kwargs: Type-specific kwargs (code, target_file, mode, error_msg,
                  feature_desc, files, git_diff, dry_run, project_root).
                  Only the kwargs that match wf_type's signature are
                  forwarded (matching the legacy behavior).

    Returns:
        Dict from run_workflow() with trace_id guaranteed to be present.
    """
    from workflows.base import run_workflow

    run_kwargs: Dict[str, Any] = {
        "goal": goal,
        "trace_id": trace_id,
    }

    # Forward type-specific kwargs (mirrors the legacy facade branches).
    if wf_type == "data":
        code = kwargs.get("code", "")
        if code:
            run_kwargs["code"] = code

    elif wf_type == "autocode":
        run_kwargs.update({
            "target_file": kwargs.get("target_file", ""),
            "mode": kwargs.get("mode", "improve"),
            "error_msg": kwargs.get("error_msg", ""),
            "feature_desc": kwargs.get("feature_desc", ""),
        })
        # [v1.0] files + git_diff + dry_run are NEW pass-through params
        # for autocode v1.1.2 (git-diff input mode + pre-flight dry run).
        files = kwargs.get("files", "")
        if files:
            run_kwargs["files"] = files
        if kwargs.get("git_diff"):
            run_kwargs["git_diff"] = True
        if kwargs.get("dry_run"):
            run_kwargs["dry_run"] = True

    elif wf_type == "understand":
        # [Bug #3] understand workflow must receive project_root — previously
        # validated but never forwarded to run_workflow, causing it to default
        # to agent root instead of the specified project directory.
        run_kwargs["project_root"] = kwargs.get("project_root", "")
        run_kwargs["skip_embeddings"] = kwargs.get("skip_embeddings", False)

    elif wf_type == "autoresearch":
        # [v1.0] autoresearch: pass target_file + project_root to the
        # experiment-driven optimization loop. target_file is the script the
        # workflow will modify + run repeatedly; project_root is the git repo
        # where the experiment branch is created.
        #
        # [v1.3 P2-2] Forward ALL autoresearch params — was only target_file +
        # project_root. Callers passing metric_name, metric_direction,
        # time_budget, branch, or results_path previously had them silently
        # dropped — the workflow ran with cfg defaults instead of the
        # caller-supplied values.
        run_kwargs["target_file"] = kwargs.get("target_file", "")
        if kwargs.get("project_root"):
            run_kwargs["project_root"] = kwargs["project_root"]
        if kwargs.get("metric_name"):
            run_kwargs["metric_name"] = kwargs["metric_name"]
        if kwargs.get("metric_direction"):
            run_kwargs["metric_direction"] = kwargs["metric_direction"]
        if kwargs.get("time_budget"):
            run_kwargs["time_budget"] = kwargs["time_budget"]
        if kwargs.get("branch"):
            run_kwargs["branch"] = kwargs["branch"]
        if kwargs.get("results_path"):
            run_kwargs["results_path"] = kwargs["results_path"]
        # [v1.4] Forward max_iterations (0 = unlimited). Type handler pulls
        # from cfg.autoresearch_max_iterations if caller didn't pass it.
        if kwargs.get("max_iterations"):
            run_kwargs["max_iterations"] = kwargs["max_iterations"]
        # [v1.6] Forward parallel_count (1 = v1.5 single-experiment mode).
        # Type handler pulls from cfg.autoresearch_parallel_count if caller
        # didn't pass it.
        if kwargs.get("parallel_count"):
            run_kwargs["parallel_count"] = kwargs["parallel_count"]

    # research + deep_research: no extra kwargs (just goal + trace_id).

    # v1.1-p1: Forward timeout to run_workflow for ALL workflow types.
    # run_workflow ignores it for autocode (which manages its own timeout
    # via invoke_with_timeout + cfg.autocode_graph_timeout). For other
    # workflows, timeout > 0 wraps graph.invoke() with a daemon-thread deadline.
    if timeout > 0:
        run_kwargs["timeout"] = timeout

    # [v3.4 #38] Forward HiTL approval flag — only when True so non-HiTL runs
    # don't pollute the initial_state with a False default that would mask any
    # restored True value from a checkpoint.
    if kwargs.get("hitl_approved"):
        run_kwargs["hitl_approved"] = True

    result = run_workflow(
        workflow_type=wf_type,
        resume=resume,
        **run_kwargs,
    )

    # Ensure trace_id is in result for downstream observability.
    if isinstance(result, dict):
        if "trace_id" not in result:
            result["trace_id"] = trace_id
        return result

    # Fallback if run_workflow returns a string or non-dict.
    return {"status": "success", "result": result, "trace_id": trace_id}


# ── Workflow metadata discovery ──────────────────────────────────────────────
# Mapping of workflow type -> graph module path. The list action iterates this
# and imports each module to read its WORKFLOW_METADATA attribute. If the
# module can't be imported (e.g. heavy optional dep missing), it shows up as
# an "error" entry rather than crashing the list action.
_WORKFLOW_MODULES: Dict[str, str] = {
    "research": "workflows.research_impl.graph",
    "data": "workflows.data_impl.graph",
    "autocode": "workflows.autocode_impl.graph",
    "deep_research": "workflows.deep_research_impl.graph",
    "understand": "workflows.understand_impl.graph",
    "autoresearch": "workflows.autoresearch_impl.graph",
}


def _get_all_workflow_metadata() -> dict:
    """Return a dict mapping workflow_type -> metadata dict (or error).

    For each workflow module in _WORKFLOW_MODULES, imports it and reads
    WORKFLOW_METADATA. If the import fails or WORKFLOW_METADATA is absent,
    returns {"name": <type>, "error": "metadata not available"}.

    Returns:
        Dict like:
            {
                "research": {"name": "Research", "version": "1.0",
                              "description": "...", "entry_point": "..."},
                "data": {"name": "data", "error": "metadata not available"},
                ...
            }
    """
    result: Dict[str, Any] = {}
    for name, module_path in _WORKFLOW_MODULES.items():
        try:
            mod = importlib.import_module(module_path)
            meta = getattr(mod, "WORKFLOW_METADATA", None)
            if meta:
                result[name] = {
                    "name": meta.get("name", name),
                    "version": meta.get("version", "?"),
                    "description": meta.get("description", ""),
                    "entry_point": meta.get("entry_point", ""),
                }
            else:
                result[name] = {"name": name, "error": "metadata not available"}
        except Exception:
            result[name] = {"name": name, "error": "metadata not available"}
    return result
