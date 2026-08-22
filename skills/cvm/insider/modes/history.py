"""Mode: history -- recent insider transactions (newest-first).

Wraps data_sources.cvm.vlmo.query_engine with bridge auto-sync + freshness.

Registered as "history" in skills.cvm.insider._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.insider._registry import register_mode


@register_mode(
    "history",
    description="Recent insider transactions (newest-first). Returns: date, role, type (buy/sell), asset, qty, price, volume.",
    include_in_all=False,
    params={
        "company": "str. Ticker, name, or CNPJ. Required.",
        "limit":   "int. Max results. Default: 50.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="insider", mode="history", params=\'{"company":"PETR4"}\')',
    ],
)
def history(company: str = "", limit: int = 50) -> dict:
    """Recent insider transactions (newest-first).

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
        limit: Max results. Default: 50.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.vlmo.query_engine import query
    r = query(company=company, limit=limit)

    # Add freshness
    from skills._freshness import add_freshness
    return add_freshness(r)
