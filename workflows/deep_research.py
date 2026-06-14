"""workflows/deep_research.py
DeepResearch workflow facade.
"""
from __future__ import annotations
import concurrent.futures
from workflows.base import run_workflow
from core.config import cfg

def run_deep_research_agent(goal: str, **kwargs) -> dict:
    """Run the deep research workflow for a given goal.

    Args:
        goal: The research question or topic.
        **kwargs: Overrides for workflow state fields (e.g. max_iterations).

    Returns:
        Final workflow state dict with at least status, result, report.
    """
    if not goal or not goal.strip():
        return {"status": "failed", "error": "Goal is required"}

    merged = {
        "iteration": 0,
        "consecutive_empty_iterations": 0,
        "budget_api_calls": cfg.deep_research_max_api_calls,
        "budget_browser_actions": cfg.deep_research_max_browser_actions,
        "budget_events": [],
        "max_iterations": cfg.deep_research_max_iterations,
        "completeness_threshold": cfg.deep_research_completeness_threshold,
        "convergence_threshold": cfg.deep_research_convergence_threshold,
        "knowledge_base": "",
        "_prev_knowledge": "",
        "completeness": 0.0,
        "converged": False,
        "sub_queries": [],
        "pending_queries": [],
        "extracted_evidence": [],
        "failed_sources": [],
        "seen_urls": [],
    }
    merged.update(kwargs)

    timeout = kwargs.get("timeout", cfg.deep_research_timeout_seconds)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(
            run_workflow,
            workflow_type="deep_research",
            goal=goal,
            trace_id=kwargs.get("trace_id", ""),
            **merged,
        )
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return {
                "status": "timeout",
                "error": f"Workflow exceeded {timeout}s timeout",
                "result": "",
                "report": "",
            }
