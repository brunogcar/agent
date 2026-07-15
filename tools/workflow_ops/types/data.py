"""tools/workflow_ops/types/data.py — The `data` type handler.

Analyze datasets with pandas/numpy, generate reports.

Validation: goal must be non-empty. Optional `code` is forwarded.
Execution: calls _execute_workflow("data", goal, trace_id, resume, code=code).
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
    "data",
    help_text="Analyze datasets with pandas/numpy, generate reports.",
)
def _type_data(
    goal: str = "",
    code: str = "",
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="data")

    return _execute_workflow(
        "data", goal, trace_id, resume,
        code=code,
    )
