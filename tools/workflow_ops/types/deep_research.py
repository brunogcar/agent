"""tools/workflow_ops/types/deep_research.py — The `deep_research` type handler.

Iterative multi-faceted research with a ReAct loop.

Validation: goal must be non-empty. No other params.
Execution: calls _execute_workflow("deep_research", goal, trace_id, resume).
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
    "deep_research",
    help_text="Iterative multi-faceted research with ReAct loop.",
)
def _type_deep_research(
    goal: str = "",
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="deep_research")

    return _execute_workflow("deep_research", goal, trace_id, resume)
