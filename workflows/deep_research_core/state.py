"""DeepResearch state schema.

Extends WorkflowState with fields specific to the iterative
research loop, budget tracking, and convergence detection.
"""
from __future__ import annotations

from typing import TypedDict

from workflows.base import WorkflowState


class DeepResearchState(WorkflowState, total=False):
    """State dict for the DeepResearch workflow.

    All fields are optional (total=False) so that LangGraph can
    merge partial updates safely.  The facade in
    ``workflows/deep_research.py`` is responsible for initialising
    every field before ``graph.invoke()``.
    """

    # ── Iteration control ──────────────────────────────────────────
    iteration: int
    """Current loop iteration (0-based)."""

    max_iterations: int
    """Hard ceiling before forced exit."""

    # ── Completeness evaluation ────────────────────────────────────
    completeness: float
    """Last LLM critique score (0-100)."""

    completeness_threshold: float
    """Score required to consider the goal answered."""

    # ── Knowledge accumulation ───────────────────────────────────────
    knowledge_base: str
    """Running synthesis string, replaced each iteration."""

    _prev_knowledge: str
    """Snapshot of *previous* knowledge_base for convergence checks."""

    pending_queries: list[str]
    """Sub-queries produced by the decompose node."""

    extracted_evidence: list[dict]
    """Raw evidence from the current search iteration.  Cleared after synthesis."""

    # ── Source tracking ────────────────────────────────────────────
    failed_sources: list[dict]
    """URLs that could not be extracted, with reason and iteration.

    Format: ``{"url": str, "reason": str, "iteration": int}``
    """

    # ── Budget & telemetry ─────────────────────────────────────────
    budget_api_calls: int
    """Remaining Tavily API calls."""

    budget_browser_actions: int
    """Remaining browser actions (navigate, click, etc.)."""

    budget_events: list[dict]
    """Audit trail of every tool selection and fallback.

    Format: ``{"iteration": int, "tool": str, "action": str, "reason": str}``
    """

    # ── Outputs ──────────────────────────────────────────────────────
    synthesis: str
    """Latest LLM synthesis text."""

    report: str
    """Final markdown report with budget audit."""

    # ── Routing (internal) ─────────────────────────────────────────
    next_node: str
    """Optional routing hint used by conditional edges."""
