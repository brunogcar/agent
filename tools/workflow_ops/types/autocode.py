"""tools/workflow_ops/types/autocode.py — The `autocode` type handler.

Fix bugs, add features, refactor code (TDD + safety). Autocode takes git
snapshots and modifies the filesystem, so this handler enforces fail-fast
parameter guards BEFORE any execution.

Validation:
  - goal must be non-empty.
  - target_file must be non-empty (always required for autocode).
  - If mode='fix_error', error_msg must be non-empty.
  - If mode='add_feature', feature_desc must be non-empty.

Execution: calls _execute_workflow("autocode", goal, trace_id, resume,
    target_file=..., mode=..., error_msg=..., feature_desc=..., files=...,
    git_diff=..., dry_run=...).
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
    "autocode",
    help_text="Fix bugs, add features, refactor code (TDD + safety). Requires target_file.",
)
def _type_autocode(
    goal: str = "",
    target_file: str = "",
    mode: str = "improve",
    error_msg: str = "",
    feature_desc: str = "",
    files: str = "",
    git_diff: bool = False,
    dry_run: bool = False,
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="autocode")

    # target_file is always required for autocode
    if not target_file or not target_file.strip():
        return _make_error(
            "target_file is required for autocode workflow",
            trace_id,
            workflow_type="autocode",
        )

    # mode-specific requirements
    if mode == "fix_error" and not error_msg:
        return _make_error(
            "error_msg is required for mode='fix_error'",
            trace_id,
            workflow_type="autocode",
            mode=mode,
        )

    if mode == "add_feature" and not feature_desc:
        return _make_error(
            "feature_desc is required for mode='add_feature'",
            trace_id,
            workflow_type="autocode",
            mode=mode,
        )

    return _execute_workflow(
        "autocode", goal, trace_id, resume,
        target_file=target_file,
        mode=mode,
        error_msg=error_msg,
        feature_desc=feature_desc,
        files=files,
        git_diff=git_diff,
        dry_run=dry_run,
    )
