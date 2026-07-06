"""workflows/autocode.py — Thin facade for the autocode workflow.

v1.1: Fixed broken facade (was unreachable for 2 versions due to dead imports
removed in v1.0.1/v1.0.2). Now delegates to base.py's run_workflow() for
tracing, checkpointing, and timeout — single entry point, no dual-entry mess.

[BACKWARD COMPAT] run_autocode_agent() is kept as a thin shim that delegates
to run_workflow(workflow_type="autocode"). This preserves the public API.
TODO (roadmap): audit callers and remove the shim once all use run_workflow()
directly. See CHANGELOG roadmap item.
"""
from __future__ import annotations

from typing import Any

# Graph + metadata (the facade's real job)
from workflows.autocode_impl.graph import build_graph, get_graph, WORKFLOW_METADATA

# State (public API — used by tests and callers)
from workflows.autocode_impl.state import AutocodeState, _default_state

__all__ = [
    "run_autocode_agent",
    "build_graph",
    "get_graph",
    "WORKFLOW_METADATA",
    "AutocodeState",
    "_default_state",
]


def run_autocode_agent(
    task: str,
    files: dict[str, str] | None = None,
    mode: str = "feature",
    target_file: str = "",
    dry_run: bool = False,
    trace_id: str = "",
) -> dict[str, Any]:
    """Run the autocode workflow.

    [v1.1] Backward-compat shim — delegates to base.py's run_workflow().
    This gets checkpoint/resume, tracing, and timeout for free, instead of
    duplicating that logic here. The previous implementation bypassed base.py,
    causing double trace creation and missing checkpoint support.

    TODO (roadmap): remove this shim once all callers use run_workflow()
    directly. See CHANGELOG.

    Args:
        task: The task description.
        files: Dictionary of file paths to content.
        mode: Task mode (feature, fix, refactor, edit, create_skill, audit).
        target_file: The target file for the operation.
        dry_run: If True, don't actually write files or commit.
        trace_id: Optional trace ID (created if empty).

    Returns:
        Dict with status, result, trace_id, commit_sha, error, etc.
    """
    from workflows.base import run_workflow

    return run_workflow(
        workflow_type="autocode",
        goal=task,
        task=task,
        files=files or {},
        mode=mode,
        target_file=target_file,
        dry_run=dry_run,
        trace_id=trace_id,
    )
