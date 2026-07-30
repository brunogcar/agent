"""Mode: strategies -- list available built-in backtest strategies.

Returns the catalog of built-in strategies with their descriptions, required
metrics, and max holding days. Used by the LLM to discover available
strategy names before calling ``run()``.

Registered as "strategies" in skills.cvm.backtest._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.backtest._registry import register_mode
from skills.cvm.backtest.helpers import BUILTIN_STRATEGIES


@register_mode(
    "strategies",
    description="List all available built-in strategies with their descriptions.",
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="backtest", mode="strategies")',
    ],
)
def strategies() -> dict:
    """List all available built-in strategies."""
    result = {
        "status": "ok",
        "strategies": [
            {
                "name": s["name"],
                "description": s["description"],
                "max_holding_days": s.get("max_holding_days", 252),
                "metrics": s.get("metrics", []),
            }
            for s in BUILTIN_STRATEGIES.values()
        ],
        "count": len(BUILTIN_STRATEGIES),
    }
    return result
