"""workflows/deep_research_impl/routes.py
Conditional routing logic for the DeepResearch cyclic graph.

v1.1.1 (#11): route_after_synthesize now reads state["converged"] instead
of recomputing via _is_converged(). The value is already computed in
node_synthesize and stored in state. Recomputing was redundant and could
diverge if the knowledge_base changed between synthesize and route.
"""
from __future__ import annotations
from workflows.deep_research_impl.state import DeepResearchState


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
    # v1.1.1 (#11): Read converged from state (computed by node_synthesize)
    converged = state.get("converged", False)
    if completeness >= threshold and converged:
        return "report"

    return "decompose"
