"""Node: notify — Send completion notification and mark workflow done.

[Fix #10] artifacts now a list of strings (was list of dicts).
v1.1.1: notify() wrapped in try/except — non-fatal (same pattern as data
workflow Fix #10). Was: notify failure crashed before node_done ran.
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_done
from core.tracer import tracer


def node_notify(state: WorkflowState) -> dict:
    """Send completion notification and mark workflow done."""
    from tools.notify import notify
    from core.citations import citations

    goal = state.get("goal", "")
    result = state.get("result", "")
    tid = state.get("trace_id", "")
    sources = citations.get_sources(tid) if tid else []

    try:
        notify(
            action="send",
            title="Research complete",
            message=f"{goal[:50]}: {result[:80]}...",
        )
    except Exception as e:
        tracer.error(tid, "notify", f"notification failed: {e}")

    artifact_urls = [s.get("url", "") for s in sources if s.get("url")]
    return node_done(state, result=result or "Research complete",
                     artifacts=artifact_urls)
