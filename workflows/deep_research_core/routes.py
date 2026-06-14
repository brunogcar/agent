"""workflows/deep_research_core/routes.py
Conditional routing logic for the DeepResearch cyclic graph.
"""
from __future__ import annotations
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.constants import (
    CONVERGENCE_SIMILARITY_THRESHOLD,
    _is_converged,
)

def route_after_synthesize(state: DeepResearchState) -> str:
    """
    Decide whether to loop back to decompose or exit to report.

    Exit conditions (in order):
    1. Hard cap: iteration >= max_iterations -> report (always)
    2. Stuck-loop: consecutive_empty_iterations >= 2 -> report
    3. Dual-gate: completeness >= threshold AND converged -> report
    4. Otherwise -> decompose (continue loop)
    """
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 10)
    if iteration >= max_iter:
        return "report"

    if state.get("consecutive_empty_iterations", 0) >= 2:
        return "report"

    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", 85.0)
    prev_knowledge = state.get("_prev_knowledge", "")
    knowledge_base = state.get("knowledge_base", "")
    converged = _is_converged(prev_knowledge, knowledge_base, CONVERGENCE_SIMILARITY_THRESHOLD)
    if completeness >= threshold and converged:
        return "report"

    return "decompose"
