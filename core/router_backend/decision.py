"""core/router_backend/decision.py -- Structured routing decision.

Extracted from core/router.py v1.0 split. No behavior change.
"""
from __future__ import annotations


class RoutingDecision:
    """Structured routing decision with fallback handling.

    Consumed by the workflow tool, the dispatcher, and the gateway.
    All fields have sensible defaults so heuristics never crash.
    """
    def __init__(self, raw: dict) -> None:
        self.workflow = raw.get("workflow", "research")
        self.tool = raw.get("tool", "web")
        self.complexity = int(raw.get("complexity", 5))
        self.reason = raw.get("reason", "")
        self.confidence = raw.get("confidence", "medium")
        self.clarifying_questions = raw.get("clarifying_questions", [])
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"RoutingDecision(workflow={self.workflow!r}, "
            f"tool={self.tool!r}, complexity={self.complexity}, "
            f"reason={self.reason!r})"
        )

    def to_dict(self) -> dict:
        return {
            "workflow": self.workflow,
            "tool": self.tool,
            "complexity": self.complexity,
            "reason": self.reason,
            "confidence": self.confidence,
        }
