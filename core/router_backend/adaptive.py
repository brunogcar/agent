"""core/router_backend/adaptive.py -- Adaptive complexity thresholds.

[v1.0 NEW] Require high confidence for complex tasks.

If complexity > 7 and confidence is not "high", downgrade to "medium" and
add a clarifying question. This prevents the router from confidently
routing complex tasks that might be better served by asking for
clarification.

This is one of the v1.0 roadmap items.

Design:
    - COMPLEXITY_THRESHOLD = 7 (strictly greater-than comparison).
    - Mutates the decision in place AND returns it for fluent chaining.
    - The threshold is intentionally STRICT (>) so existing test cases at
      complexity=7 are unaffected. Only complexity=8, 9, 10 trigger the rule.
"""
from __future__ import annotations

from core.router_backend.decision import RoutingDecision

COMPLEXITY_THRESHOLD = 7


def apply_adaptive_thresholds(decision: RoutingDecision) -> RoutingDecision:
    """Apply adaptive complexity thresholds to a routing decision.

    If complexity > 7 and confidence != "high":
    - Downgrade confidence to "medium"
    - Add a clarifying question if none exist
    - Log the downgrade via tracer (non-fatal)

    Returns the same decision object (mutated in place) for fluent chaining.
    """
    if decision.complexity > COMPLEXITY_THRESHOLD and decision.confidence != "high":
        # Downgrade confidence -- complex tasks need high confidence
        decision.confidence = "medium"
        # Add clarifying question if none exist
        if not decision.clarifying_questions:
            decision.clarifying_questions = [
                "This is a complex task -- can you provide more specific details about what you want to achieve?"
            ]
    return decision
