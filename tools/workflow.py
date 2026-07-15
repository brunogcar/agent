"""tools/workflow.py — Workflow meta-tool (v1.0).

Thin @tool facade. Routes all workflow actions to handlers in
workflow_ops/actions/ via the DISPATCH dict. The `run` action further
dispatches into TYPE_DISPATCH (workflow_ops/types/) based on the `type`
parameter — two-level dispatch.

v1.0 changes (the @meta_tool refactor):
  - Now a meta-tool with 5 actions: run | list | status | cancel | history.
  - @meta_tool auto-generates the action: Literal[...] type annotation and
    the docstring's action list from DISPATCH.
  - BREAKING: the old `type` parameter alone no longer works. You must use
    `action="run"` + `type="research"` (or other type). The old
    `workflow(type="research", goal="...")` call MUST be rewritten as
    `workflow(action="run", type="research", goal="...")`.
  - New params: files (JSON dict of filename→content for autocode
    pass-through), git_diff (autocode v1.1.2 git-diff input mode),
    dry_run (pre-flight: validate params + routing without executing).
  - All implementation logic moved to workflow_ops/ subpackage.

NOT parallel-safe — workflows are long-running blocking calls. Do NOT add
to PARALLEL_SAFE.
The router already routes to `workflow` for workflow intents; no router
changes needed for v1.0.

[DESIGN] The `type` param is kept as `type` (not renamed to avoid shadowing
the Python builtin in a way that breaks existing call sites). The breaking
change is that `type` alone no longer works — callers must use
`action="run"` + `type="..."`.
"""
from __future__ import annotations

import time

from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import workflow_ops to trigger DISPATCH + TYPE_DISPATCH auto-discovery
# BEFORE @meta_tool reads DISPATCH.
from tools import workflow_ops  # noqa: F401
from tools.workflow_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("workflow", {}),
    doc_sections=[
        "WORKFLOW TOOL — Launch and manage LangGraph workflows:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Run a workflow | workflow(run, type=research) | Execute a multi-step autonomous workflow |",
        " | List available workflows | workflow(list) | Show all workflows + their metadata |",
        " | Check workflow status | workflow(status, trace_id=...) | Check checkpoint for a running/completed workflow |",
        " | Cancel a workflow | workflow(cancel, trace_id=...) | Set cancellation flag (autocode only) |",
        " | Show recent runs | workflow(history) | Query tracer for recent workflow executions |",
        "",
        "Workflow types (for action=run): research, data, autocode, deep_research, understand, autoresearch, auto",
        "NOT parallel-safe — workflows are long-running blocking calls.",
    ],
)
def workflow(
    action: str = "",
    type: str = "",
    goal: str = "",
    # data workflow
    code: str = "",
    # autocode workflow
    target_file: str = "",
    mode: str = "improve",
    error_msg: str = "",
    feature_desc: str = "",
    files: str = "",
    git_diff: bool = False,
    dry_run: bool = False,
    # understand / autoresearch workflow
    project_root: str = "",
    # common
    trace_id: str = "",
    resume: bool = False,
) -> dict:
    """Workflow meta-tool — run | list | status | cancel | history.

    Launch and manage LangGraph workflows. The `run` action dispatches
    into a second-level registry (TYPE_DISPATCH) based on the `type`
    parameter — see workflow_ops/types/ for the per-type handlers.

    Args:
        action: Which action to perform. Auto-restricted by @meta_tool to
                the registered action names (run | list | status | cancel | history).
        type: Workflow type — only used by action='run'. One of:
              research | data | autocode | deep_research | understand |
              autoresearch | auto.
        goal: Goal text — required for action='run' (and routed types).
        code: Optional code string — forwarded to the data workflow.
        target_file: Required for autocode + autoresearch workflows.
        mode: Autocode mode — improve (default) | fix_error | add_feature.
        error_msg: Required when mode='fix_error'.
        feature_desc: Required when mode='add_feature'.
        files: JSON dict of filename→content — autocode pass-through.
        git_diff: Use git-diff input mode (autocode v1.1.2).
        dry_run: Pre-flight: validate params + routing without executing.
        project_root: Required for understand; optional for autoresearch.
        trace_id: Observability threading ID. Auto-generated if missing.
        resume: Resume from checkpoint.

    Returns:
        Dict with status="success" | "error" | "routed" |
        "needs_clarification". Every response includes trace_id.
    """
    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "workflow", f"action={action} type={type}")

    if not action:
        return {
            "status": "error",
            "error": "action is required (run | list | status | cancel | history)",
            "trace_id": trace_id,
        }

    dispatch = DISPATCH.get("workflow", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return {
            "status": "error",
            "error": f"Unknown action '{action}'. Use: {valid_actions}",
            "trace_id": trace_id,
        }

    handler = op_info["func"]

    # Forward every facade param to the handler. Handlers pick what they
    # need via **kwargs — no per-action conditional branches needed here.
    kwargs = {
        "type": type,
        "goal": goal,
        "code": code,
        "target_file": target_file,
        "mode": mode,
        "error_msg": error_msg,
        "feature_desc": feature_desc,
        "files": files,
        "git_diff": git_diff,
        "dry_run": dry_run,
        "project_root": project_root,
        "trace_id": trace_id,
        "resume": resume,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        tracer.error(trace_id, "workflow", f"Action '{action}' failed: {e}")
        return {
            "status": "error",
            "error": f"Workflow action failed: {e}",
            "trace_id": trace_id,
        }

    if not isinstance(result, dict):
        return {
            "status": "error",
            "error": f"Handler returned {type(result).__name__}, expected dict.",
            "trace_id": trace_id,
        }

    if result.get("status") == "error":
        tracer.step(trace_id, "workflow", f"action={action}:failed")
    else:
        tracer.step(trace_id, "workflow", f"action={action}:complete")

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
