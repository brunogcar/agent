"""tools/workflow_ops/actions/run.py — The `run` action.

This is the entry point for actually executing a workflow. It receives the
`type` parameter and dispatches into TYPE_DISPATCH via the second-level
registry.

Two-level dispatch:
  workflow(action="run", type="research", ...)  →  THIS handler  →  TYPE_DISPATCH["research"]

Each type handler validates its specific params and calls _execute_workflow()
to invoke workflows.base.run_workflow.

[DESIGN] The `run` action is intentionally thin — it does NOT perform
workflow-specific validation (target_file, project_root, etc.). That
validation lives in the type handler so it's co-located with the type's
other logic. The run action only validates that `type` is non-empty and
registered.

[DESIGN] **kwargs forwarding: the run action signature includes a fixed
list of well-known params (code, target_file, etc.) PLUS **kwargs. The
**kwargs catch-all lets list-valued params (e.g. `steps` for type="compose")
flow through without polluting the MCP schema — FastMCP doesn't handle
list-typed params well, so `steps` stays in **kwargs and the compose type
handler reads it from there.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops._type_registry import TYPE_DISPATCH
from tools.workflow_ops.helpers import _ensure_trace_id, _make_error


@register_action(
    "workflow", "run",
    help_text="""run — Launch a multi-step autonomous workflow.
Required: type (research|data|autocode|deep_research|understand|autoresearch|auto|compose), goal
Optional: code (data), target_file/mode/error_msg/feature_desc/files/git_diff/dry_run (autocode),
          project_root (understand/autoresearch), trace_id, resume, timeout,
          steps (compose — list of step dicts, each {type, goal, ...})
Returns: {status, workflow, trace_id, ...} (workflow-specific)""",
    examples=[
        'workflow(action="run", type="research", goal="Survey LLM agent frameworks")',
        'workflow(action="run", type="data", goal="Analyze sales.csv", code="print(df.head())")',
        'workflow(action="run", type="autocode", goal="Fix login bug", target_file="auth.py", mode="fix_error", error_msg="KeyError: user")',
        'workflow(action="run", type="understand", goal="Map codebase", project_root="/path/to/repo")',
        'workflow(action="run", type="auto", goal="Find recent papers on RAG")',
        'workflow(action="run", type="compose", goal="Survey + analyze", steps=[{"type":"research","goal":"Survey X"},{"type":"data","goal":"Analyze","code":"print(1)"}])',
    ],
)
def _action_run(
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
    # per-workflow timeout (0 = use workflow default; autocode ignores this
    # and uses cfg.autocode_graph_timeout instead)
    timeout: int = 0,
    **kwargs,
) -> dict:
    """Run a workflow of the given type.

    Validates `type` is non-empty and registered in TYPE_DISPATCH, then
    forwards all parameters to the type handler. The type handler is
    responsible for type-specific validation and calling _execute_workflow().
    """
    trace_id = _ensure_trace_id(trace_id, goal)

    if not type or not type.strip():
        return _make_error(
            "type is required for action='run'",
            trace_id,
            valid_types=sorted(TYPE_DISPATCH.keys()),
        )

    wf_type = type.strip().lower()

    if wf_type not in TYPE_DISPATCH:
        return _make_error(
            f"Invalid workflow type '{type}'. Valid: {sorted(TYPE_DISPATCH.keys())}",
            trace_id,
            valid_types=sorted(TYPE_DISPATCH.keys()),
        )

    type_handler = TYPE_DISPATCH[wf_type]["func"]
    return type_handler(
        goal=goal,
        code=code,
        target_file=target_file,
        mode=mode,
        error_msg=error_msg,
        feature_desc=feature_desc,
        files=files,
        git_diff=git_diff,
        dry_run=dry_run,
        project_root=project_root,
        trace_id=trace_id,
        resume=resume,
        timeout=timeout,
        **kwargs,
    )
