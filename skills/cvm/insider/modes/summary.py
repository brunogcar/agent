"""Mode: summary -- net buy/sell summary per month (last 24 months).

Wraps data_sources.cvm.vlmo.query_engine with bridge auto-sync + freshness.
Computes overall net_volume + insider sentiment (buying/selling/neutral).

Registered as "summary" in skills.cvm.insider._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.insider._registry import register_mode


@register_mode(
    "summary",
    description="Net buy/sell summary per month (last 24 months). Shows insider sentiment trend.",
    include_in_all=True,
    params={
        "company": "str. Required.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="insider", mode="summary", params=\'{"company":"PETR4"}\')',
    ],
)
def summary(company: str = "") -> dict:
    """Net buy/sell summary per month (last 24 months).

    Shows insider sentiment trend — are insiders net buyers or sellers?

    Args:
        company: Ticker, name, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.vlmo.query_engine import query
    r = query(company=company, summary=True)

    # Compute overall net sentiment
    if r.get("status") == "ok" and r.get("monthly"):
        total_bought = sum(m.get("volume_bought") or 0 for m in r["monthly"])
        total_sold = sum(m.get("volume_sold") or 0 for m in r["monthly"])
        r["net_volume"] = total_bought - total_sold
        r["total_volume_bought"] = total_bought
        r["total_volume_sold"] = total_sold
        r["sentiment"] = ("buying" if total_bought > total_sold
                          else "selling" if total_sold > total_bought
                          else "neutral")

    from skills._freshness import add_freshness
    return add_freshness(r)
