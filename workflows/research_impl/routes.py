"""Routing functions for the research workflow."""
from __future__ import annotations

from workflows.base import WorkflowState


def route_after_search(state: WorkflowState) -> str:
    """After search: always synthesize (even with empty results from memory)."""
    sr = state.get("search_results", "")
    mc = state.get("memory_context", "")
    if not sr and not mc:
        return "failed"
    return "synthesize"


def route_after_synthesize(state: WorkflowState) -> str:
    """After synthesis: generate report, then store."""
    if state.get("status") == "failed":
        return "failed"
    return "report"
