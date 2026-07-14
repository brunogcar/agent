"""core/router_backend/complexity.py -- Quick complexity scoring via the Router role.

Extracted from core/router.py v1.0 split. Standalone function:
    - classify_complexity(goal) -> int  (1-10, default 5)
"""
from __future__ import annotations

from core.llm import llm
from core.config import cfg


def classify_complexity(goal: str) -> int:
    """Quick complexity score (1-10) for a goal.

    Standalone function (v1.0 split -- was TaskRouter.classify_complexity).
    Uses the Router classify role.

    Returns 5 (default mid-point) if the LLM call fails or returns a non-integer.
    """
    r = llm.complete(
        role="router",
        system=(
            "Rate the complexity of this task on a scale of 1-10. "
            "Output only a single integer. Nothing else."
            "\n1-3: single tool, clear input/output"
            "\n4-6: multi-step, predictable"
            "\n7-9: complex, multiple tools, uncertainty"
            "\n10: requires human judgment"
        ),
        user=goal,
        timeout=cfg.router_timeout,
    )
    if r.ok:
        try:
            return max(1, min(10, int(r.text.strip())))
        except (ValueError, TypeError):
            pass
    return 5  # default
