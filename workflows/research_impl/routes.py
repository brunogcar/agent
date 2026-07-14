"""Routing functions for the research workflow."""
from __future__ import annotations

from workflows.base import WorkflowState


def route_after_search(state: WorkflowState) -> str:
    """After search: route to synthesize if we have any source material; END if both search and memory are empty."""
    sr = state.get("search_results", "")
    mc = state.get("memory_context", "")
    if not sr and not mc:
        return "failed"
    return "synthesize"


def route_after_synthesize(state: WorkflowState) -> str:
    """After synthesis: route to trim (v1.1), then report, then store."""
    if state.get("status") == "failed":
        return "failed"
    return "trim"
