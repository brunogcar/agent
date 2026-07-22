"""tools/workflow_ops/types/autoresearch.py — The `autoresearch` type handler.

Autonomous experiment-driven optimization (modify → run → measure →
keep/discard → repeat). Inspired by karpathy/autoresearch.

Validation:
  - goal must be non-empty.
  - target_file must be non-empty (the script the workflow will modify
    + run repeatedly).

Execution: calls _execute_workflow("autoresearch", goal, trace_id, resume,
    target_file=target_file, project_root=project_root, metric_name=...,
    metric_direction=..., time_budget=..., branch=..., results_path=...,
    max_iterations=..., parallel_count=...).

[v1.3 P2-2] Forwards ALL autoresearch params to `_execute_workflow` (was:
only target_file + project_root). Callers passing metric_name,
metric_direction, time_budget, branch, or results_path previously had them
silently dropped — the workflow ran with cfg defaults instead.

[v1.4] Forwards `max_iterations` (caller-set hard cap on experiments).
0 = unlimited (legacy v1.3 behavior). Also picked up from
`cfg.autoresearch_max_iterations` if not passed.

[v1.6] Forwards `parallel_count` (N parallel proposals + subprocesses per
iteration). 1 = v1.5 single-experiment mode. Also picked up from
`cfg.autoresearch_parallel_count` if not passed.
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
    max_iterations: int = 0,
    parallel_count: int = 1,
    reflect_interval: int = 0,
    convergence_window: int = 10,
    convergence_epsilon: float = 0.001,
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
    #
    # [v1.4] Forward max_iterations (0 = unlimited). Pulled from
    # cfg.autoresearch_max_iterations if caller didn't pass it.
    if max_iterations == 0:
        from core.config import cfg
        max_iterations = int(getattr(cfg, "autoresearch_max_iterations", 0))

    # [v1.6] Forward parallel_count (1 = v1.5 single-experiment mode).
    # Pulled from cfg.autoresearch_parallel_count if caller didn't pass it.
    if parallel_count == 1:
        from core.config import cfg
        parallel_count = int(getattr(cfg, "autoresearch_parallel_count", 1))

    # [v1.2.2 / autoresearch v1.11 A8] Forward the 3 loop-control knobs that
    # were previously NOT forwarded by this type handler.
    #   - reflect_interval: was cfg-only (not a state field pre-v1.11). Now
    #     a state field — callers can override per-invocation via
    #     run_workflow(reflect_interval=10). 0 = use cfg default.
    #   - convergence_window + convergence_epsilon: were state fields but the
    #     type handler didn't forward them, so per-call overrides were silently
    #     dropped (callers had to use env vars). Now forwarded.

    return _execute_workflow(
        "autoresearch", goal, trace_id, resume,
        target_file=target_file,
        project_root=project_root,
        metric_name=metric_name,
        metric_direction=metric_direction,
        time_budget=time_budget if time_budget > 0 else None,
        branch=branch,
        results_path=results_path,
        max_iterations=max_iterations,
        parallel_count=parallel_count,
        reflect_interval=reflect_interval,
        convergence_window=convergence_window,
        convergence_epsilon=convergence_epsilon,
    )
