"""tools/workflow_ops/types/understand.py — The `understand` type handler.

Build a Codebase Knowledge Graph via AST parsing. Requires project_root to
know where to scan and where to store artifacts.

Validation:
  - goal must be non-empty.
  - project_root must be non-empty (always required for understand).

Execution: calls _execute_workflow("understand", goal, trace_id, resume,
    project_root=project_root).

[Bug #3] project_root must be forwarded to run_workflow — previously
validated but never forwarded, causing understand to default to agent root
instead of the specified project directory. _execute_workflow handles this
correctly.
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
    "understand",
    help_text="Build a Codebase Knowledge Graph via AST parsing. Requires project_root.",
)
def _type_understand(
    goal: str = "",
    project_root: str = "",
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="understand")

    if not project_root or not project_root.strip():
        return _make_error(
            "project_root is required for understand workflow",
            trace_id,
            workflow_type="understand",
        )

    return _execute_workflow(
        "understand", goal, trace_id, resume,
        project_root=project_root,
    )
