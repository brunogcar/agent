"""tools/workflow_ops/types/autoresearch.py — The `autoresearch` type handler.

Autonomous experiment-driven optimization (modify → run → measure →
keep/discard → repeat). Inspired by karpathy/autoresearch.

Validation:
  - goal must be non-empty.
  - target_file must be non-empty (the script the workflow will modify
    + run repeatedly).

Execution: calls _execute_workflow("autoresearch", goal, trace_id, resume,
    target_file=target_file, project_root=project_root, metric_name=...,
    metric_direction=..., time_budget=..., branch=..., results_path=...).

[v1.3 P2-2] Forwards ALL autoresearch params to `_execute_workflow` (was:
only target_file + project_root). Callers passing metric_name,
metric_direction, time_budget, branch, or results_path previously had them
silently dropped — the workflow ran with cfg defaults instead.
"""
from __future__ import annotations

from tools.workflow_ops._type_registry import register_type
from tools.workflow_ops.helpers import (
    _ensure_trace_id,
    _execute_workflow,
    _make_error,
    _validate_goal,
)


@register_type(
    "autoresearch",
    help_text="Autonomous experiment-driven optimization. Requires target_file.",
)
def _type_autoresearch(
    goal: str = "",
    target_file: str = "",
    project_root: str = "",
    metric_name: str = "",
    metric_direction: str = "",
    time_budget: int = 0,
    branch: str = "",
    results_path: str = "",
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="autoresearch")

    if not target_file or not target_file.strip():
        return _make_error(
            "target_file is required for autoresearch workflow",
            trace_id,
            workflow_type="autoresearch",
        )

    # [v1.3 P2-2] Forward ALL autoresearch params — was only target_file +
    # project_root. Callers passing metric_name, metric_direction,
    # time_budget, branch, or results_path previously had them silently
    # dropped. _execute_workflow's autoresearch branch picks them up from
    # kwargs and forwards them to run_workflow.
    return _execute_workflow(
        "autoresearch", goal, trace_id, resume,
        target_file=target_file,
        project_root=project_root,
        metric_name=metric_name,
        metric_direction=metric_direction,
        time_budget=time_budget if time_budget > 0 else None,
        branch=branch,
        results_path=results_path,
    )
