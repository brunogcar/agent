"""Mode: listing -- list available event categories.

Registered as "listing" in skills.investsite._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

[v1.1] Moved verbatim from the former skills/investsite/investsite.py
monolith. Imports EVENT_CATEGORIES from parsers.py (unchanged).
"""
from __future__ import annotations

from skills.investsite._registry import register_mode
from skills.investsite.parsers import EVENT_CATEGORIES


@register_mode(
    "listing",
    description="List available event categories.",
    include_in_all=False,
    params={
        "ticker": "str. Optional (for reference).",
    },
    examples=[
        'skill(domain="investsite", mode="listing")',
    ],
)
def listing(ticker: str = "") -> dict:
    """List available event categories for a ticker."""
    return {
        "status": "ok",
        "ticker": ticker.strip().upper() if ticker else "",
        "categories": EVENT_CATEGORIES,
        "note": "Use mode='events' with categoria param to fetch a specific category.",
    }
