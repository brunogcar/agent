"""Mode: score -- governance score (% Sim/Não/Parcialmente).

Wraps data_sources.cvm.cgvn.query_engine with bridge auto-sync + freshness.

Registered as "score" in skills.cvm.governance._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.governance._registry import register_mode


@register_mode(
    "score",
    description=(
        "Governance score: % of practices adopted (Sim), partial "
        "(Parcialmente), not adopted (Não)."
    ),
    include_in_all=True,
    params={
        "company": "str. Required.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="governance", mode="score", params=\'{"company":"PETR4"}\')',
    ],
)
def score(company: str = "") -> dict:
    """Governance score — % of practices adopted.

    Returns: total_practices, adopted_sim, adopted_nao, adopted_parcialmente,
    score_pct (% Sim), partial_pct, not_adopted_pct.

    Args:
        company: Ticker, name, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.cgvn.query_engine import query
    r = query(company=company, score=True)

    from skills._freshness import add_freshness
    return add_freshness(r)
