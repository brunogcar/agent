"""tools/workflow_ops/types/research.py — The `research` type handler.

Gather info from the web, synthesize findings.

Validation: goal must be non-empty. No other params.
Execution: calls _execute_workflow("research", goal, trace_id, resume).
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
    "research",
    help_text="Gather info from web, synthesize findings.",
)
def _type_research(
    goal: str = "",
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="research")

    return _execute_workflow("research", goal, trace_id, resume)
