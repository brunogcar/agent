"""Mode: practices -- all governance practices for the latest filing.

Wraps data_sources.cvm.cgvn.query_engine with bridge auto-sync + freshness.

Registered as "practices" in skills.cvm.governance._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.governance._registry import register_mode


@register_mode(
    "practices",
    description="All governance practices for latest filing (recommended vs adopted).",
    include_in_all=False,
    params={
        "company": "str. Ticker, name, or CNPJ. Required.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="governance", mode="practices", params=\'{"company":"PETR4"}\')',
    ],
)
def practices(company: str = "") -> dict:
    """All governance practices for the latest filing.

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.cgvn.query_engine import query
    r = query(company=company)

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)
