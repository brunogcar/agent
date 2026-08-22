"""Mode: by_role -- insider transactions grouped by role (Tipo_Cargo).

Wraps data_sources.cvm.vlmo.query_engine with bridge auto-sync + freshness.

Registered as "by_role" in skills.cvm.insider._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.insider._registry import register_mode


@register_mode(
    "by_role",
    description="Insider transactions grouped by role (Tipo_Cargo). Shows total bought/sold per role.",
    include_in_all=False,
    params={
        "company": "str. Required.",
        "limit":   "int. Max roles. Default: 50.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="insider", mode="by_role", params=\'{"company":"PETR4"}\')',
    ],
)
def by_role(company: str = "", limit: int = 50) -> dict:
    """Insider transactions grouped by role (Tipo_Cargo).

    Shows total bought/sold per role — directors, officers, controlling
    shareholders, etc.

    Args:
        company: Ticker, name, or CNPJ. Required.
        limit: Max roles. Default: 50.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.vlmo.query_engine import query
    r = query(company=company, limit=limit, by_role=True)

    from skills._freshness import add_freshness
    return add_freshness(r)
