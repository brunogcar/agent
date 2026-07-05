"""Node: distill — Extract procedural rules from completed research.

[Fix #8] Removed dead `status == "failed"` check — node_distill only runs
on success paths (after node_store, which only runs if result exists).
The check was dead code.
"""
from __future__ import annotations

from workflows.base import WorkflowState


def node_distill(state: WorkflowState) -> dict:
    """Extract procedural rules from the completed research workflow.

    [Fix #8] Removed `if state.get("status") == "failed": return state`
    — this node only runs on the success path (after store → distill edge).
    The check was dead code that could never fire.
    """
    from core.memory_backend.procedural.distill import distill_workflow

    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    result = state.get("result", "")

    if not result:
        return {}

    trace_text = f"GOAL: {goal}\n\nOUTCOME: Success\n\nSYNTHESIS:\n{result[:2000]}"

    try:
        # Non-blocking best-effort distillation
        distill_workflow(trace_text=trace_text, trace_id=tid)
    except Exception:
        pass  # Never fail the workflow if distillation fails

    return {}
