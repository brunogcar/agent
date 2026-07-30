"""Mode: by_chapter -- practices grouped by chapter with adoption counts.

Wraps data_sources.cvm.cgvn.query_engine with bridge auto-sync + freshness.

Registered as "by_chapter" in skills.cvm.governance._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.governance._registry import register_mode


@register_mode(
    "by_chapter",
    description="Practices grouped by chapter (Capitulo) with adoption counts.",
    include_in_all=False,
    params={
        "company": "str. Required.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="governance", mode="by_chapter", params=\'{"company":"PETR4"}\')',
    ],
)
def by_chapter(company: str = "") -> dict:
    """Practices grouped by chapter with adoption counts.

    Args:
        company: Ticker, name, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.cgvn.query_engine import query
    r = query(company=company, by_chapter=True)

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)
