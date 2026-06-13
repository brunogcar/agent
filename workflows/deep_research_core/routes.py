"""workflows/deep_research_core/routes.py"""
from __future__ import annotations
from typing import Dict, Any
from workflows.deep_research_core.state import DeepResearchState


def route_after_synthesize(state: DeepResearchState) -> str:
    """Route after synthesis.

    Exit conditions (in order):
      1. Hard cap: iteration >= max_iterations -> report (always)
      2. Stuck loop: 2+ consecutive empty iterations -> report
      3. Dual-gate: completeness >= threshold AND converged -> report
      4. Otherwise: -> search (loop)
    """
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 10)
    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", 85.0)
    converged = state.get("converged", False)
    consecutive_empty = state.get("consecutive_empty_iterations", 0)

    # Hard cap — always exit
    if iteration >= max_iter:
        return "report"

    # Stuck loop — no progress for 2+ iterations
    if consecutive_empty >= 2:
        return "report"

    # Dual-gate: completeness AND convergence
    if completeness >= threshold and converged:
        return "report"

    return "search"
