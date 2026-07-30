"""Mode: history -- individual dividend events from B3 (cash dividends).

Returns: rate, approved_on, payment_date, last_date_prior, label, related_to.
The label field distinguishes Dividendo vs JCP (Juros sobre Capital Próprio).

Delegates to data_sources.b3.dividends.query_engine.dividends.

Registered as "history" in skills.cvm.dividends._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.dividends._registry import register_mode


@register_mode(
    "history",
    description="Individual dividend events (rate, dates, label Dividendo/JCP) from B3.",
    include_in_all=False,
    params={
        "company": "str. B3 ticker (PETR4). Required.",
        "limit":   "int. Max events. Default: 50.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="dividends", mode="history", params=\'{"company":"PETR4"}\')',
    ],
)
def history(company: str = "", limit: int = 50) -> dict:
    """Individual dividend events from B3 (cash dividends).

    Returns: rate, approved_on, payment_date, last_date_prior, label, related_to.
    The label field distinguishes Dividendo vs JCP (Juros sobre Capital Próprio).

    Delegates to data_sources.b3.dividends.query_engine.dividends.
    """
    if not company:
        return {"status": "error", "error": "company (ticker) is required"}

    from data_sources.b3.dividends.query_engine import dividends as b3_dividends
    return b3_dividends(ticker=company, limit=limit)
