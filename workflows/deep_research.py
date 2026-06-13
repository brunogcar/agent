"""Thin facade for the DeepResearch workflow.

Mirrors the pattern used by ``workflows/autocode.py``:
the facade initialises workflow-specific defaults and delegates to
``run_workflow()`` in ``workflows/base.py``.
"""
from __future__ import annotations

from core.config import cfg
from workflows.base import run_workflow


def run_deep_research_agent(goal: str, trace_id: str = "", **kwargs) -> dict:
    """Run the DeepResearch workflow for a given goal.

    Initialises all DeepResearch-specific state fields with sensible
    defaults before invoking the LangGraph graph.

    Args:
        goal: The research question or topic.
        trace_id: Optional existing trace ID (fresh one created if empty).
        **kwargs: Override any default state field.

    Returns:
        Final workflow result dict with ``report``, ``result``, ``status``, etc.
    """
    defaults = {
        "iteration": 0,
        "max_iterations": cfg.deep_research_max_iterations,
        "completeness": 0.0,
        "completeness_threshold": cfg.deep_research_completeness_threshold,
        "knowledge_base": "",
        "_prev_knowledge": "",
        "pending_queries": [],
        "extracted_evidence": [],
        "failed_sources": [],
        "budget_api_calls": cfg.deep_research_max_api_calls,
        "budget_browser_actions": cfg.deep_research_max_browser_actions,
        "budget_events": [],
        "synthesis": "",
        "report": "",
    }

    merged = {**defaults, **kwargs}

    return run_workflow(
        workflow_type="deep_research",
        goal=goal,
        trace_id=trace_id,
        **merged,
    )
