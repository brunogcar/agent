"""workflows/deep_research_core/routes.py
Conditional routing logic for the DeepResearch cyclic graph.
"""
from __future__ import annotations
from difflib import SequenceMatcher
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.constants import CONVERGENCE_SIMILARITY_THRESHOLD


def _is_converged(old_knowledge: str, new_knowledge: str, threshold: float = CONVERGENCE_SIMILARITY_THRESHOLD) -> bool:
    """Check if two knowledge strings are sufficiently similar to indicate convergence.

    Uses difflib.SequenceMatcher for a conservative similarity estimate.
    With the _merge_knowledge replace semantics, knowledge_base stays bounded
    to ~2-4K chars, making this O(N) in practice.
    """
    if not old_knowledge or not new_knowledge:
        return False
    return SequenceMatcher(None, old_knowledge, new_knowledge).ratio() >= threshold


def route_after_synthesize(state: DeepResearchState) -> str:
    """Decide whether to continue the loop or exit to report.

    Exit conditions (in order of priority):
      1. Hard cap: iteration >= max_iterations → report (always)
      2. Stuck loop: consecutive_empty_iterations >= 2 → report
      3. Dual-gate: completeness >= threshold AND converged → report
      4. Otherwise → decompose (continue loop)

    The dual-gate requires BOTH completeness and convergence to be met.
    This prevents premature exit on a high score before knowledge has
    actually stabilized, or on convergence before the goal is answered.
    """
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 10)

    # Hard cap — always exit
    if iteration >= max_iter:
        return "report"

    # Stuck loop — no evidence for 2 consecutive iterations
    if state.get("consecutive_empty_iterations", 0) >= 2:
        return "report"

    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", 85.0)
    converged = _is_converged(
        state.get("_prev_knowledge", ""),
        state.get("knowledge_base", ""),
        state.get("convergence_threshold", CONVERGENCE_SIMILARITY_THRESHOLD),
    )

    # Dual-gate: completeness AND convergence
    if completeness >= threshold and converged:
        return "report"

    return "decompose"
