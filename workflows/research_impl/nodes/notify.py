"""Node: notify — Send completion notification and mark workflow done.

[Fix #10] artifacts now a list of strings (was list of dicts).
LangGraph consumers expect artifacts as list[str], not list[dict].
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_done


def node_notify(state: WorkflowState) -> dict:
    """Send completion notification and mark workflow done.

    [Fix #10] artifacts is now a list of strings (URLs), not list of dicts.
    Consumers (run_workflow, base.py) expect list[str].
    """
    from tools.notify import notify
    from core.citations import citations

    goal = state.get("goal", "")
    result = state.get("result", "")
    tid = state.get("trace_id", "")
    sources = citations.get_sources(tid) if tid else []

    notify(
        action="send",
        title="Research complete",
        message=f"{goal[:50]}: {result[:80]}...",
    )

    # [Fix #10] artifacts as list of strings (URLs), not list of dicts.
    # Was: artifacts=[{"sources": sources}]
    # Now: artifacts=[s.get("url", "") for s in sources if s.get("url")]
    artifact_urls = [s.get("url", "") for s in sources if s.get("url")]
    return node_done(state, result=result or "Research complete",
                     artifacts=artifact_urls)
