"""Conditional edge routing for the DeepResearch graph.

All route functions are pure: they read state and return a string
that must exist in the ``path_map`` passed to
``add_conditional_edges``.  Using a ``path_map`` guarantees that
LangGraph validates the routing at graph-compile time rather than
leaving silent END fallbacks at runtime.
"""
from __future__ import annotations

import logging

from core.config import cfg
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.constants import CONVERGENCE_SIMILARITY_THRESHOLD
from workflows.base import node_step

logger = logging.getLogger(__name__)


def route_after_synthesize(state: DeepResearchState) -> str:
    """Decide whether to loop back to search or proceed to the report.

    Dual-gate exit strategy:
    1. **Completeness gate**: LLM critique score ≥ threshold.
    2. **Convergence gate**: Knowledge base has stabilised
       (SequenceMatcher ratio > threshold) OR hard iteration cap reached.

    The loop exits only when **both** gates are satisfied, or when the
    hard iteration cap is reached regardless of score.

    Args:
        state: Workflow state after the synthesize node.

    Returns:
        One of ``"search"``, ``"report"``, or ``"failed"``.
    """
    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", cfg.deep_research_completeness_threshold)
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", cfg.deep_research_max_iterations)
    prev_knowledge = state.get("_prev_knowledge", "")
    knowledge_base = state.get("knowledge_base", "")

    # Hard cap — always exit
    if iteration >= max_iter:
        node_step(state, "route", f"hard cap reached ({iteration}/{max_iter}) → report")
        return "report"

    # Convergence check
    converged = _is_converged(prev_knowledge, knowledge_base)

    # Dual-gate: completeness AND (convergence OR max_iter)
    if completeness >= threshold and (converged or iteration >= max_iter):
        node_step(
            state,
            "route",
            f"completeness={completeness:.0f}≥{threshold} & converged={converged} → report",
        )
        return "report"

    # Continue looping
    node_step(
        state,
        "route",
        f"completeness={completeness:.0f}<{threshold} | converged={converged} → search",
    )
    return "search"


def _is_converged(old: str, new: str) -> bool:
    """Check if knowledge_base has stabilised between iterations."""
    if not old or not new:
        return False
    import difflib
    ratio = difflib.SequenceMatcher(None, old, new).ratio()
    return ratio > CONVERGENCE_SIMILARITY_THRESHOLD
