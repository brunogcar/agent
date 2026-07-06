"""Node: notify — Send completion notification and mark the workflow done.

[Fix #8/#10] notify() is wrapped in try/except so a notification failure does
not prevent node_done() from marking the workflow successful. The analysis
itself already succeeded; a notification hiccup should not flip the result
to failed. (Previously a notify() exception would crash node_notify before
node_done ran, surfacing as a workflow failure with no result.)
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_done
from core.tracer import tracer


def node_notify(state: WorkflowState) -> dict:
    """Send completion notification and mark the workflow done."""
    from tools.notify import notify

    goal = state.get("goal", "")
    result = state.get("result", "") or state.get("output", "")
    tid = state.get("trace_id", "")

    try:
        notify(
            action="send",
            title="Data analysis complete",
            message=f"{goal[:50]}: {result[:80]}",
        )
    except Exception as e:
        # [Fix #10] Notification failure is non-fatal — the analysis succeeded.
        tracer.error(tid, "notify", f"notification failed: {e}")

    return node_done(state, result=result or "Data analysis complete")
