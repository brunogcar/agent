"""Mode: announcements -- official CVM IPE filings related to dividends.

Searches IPE for events with keyword "dividendo" (case-insensitive) in the
assunto (subject) field. Also accepts company filter.

Delegates to data_sources.cvm.ipe.query_engine.query.

Registered as "announcements" in skills.cvm.dividends._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.dividends._registry import register_mode


@register_mode(
    "announcements",
    description="Official CVM IPE filings related to dividends (keyword search).",
    include_in_all=False,
    params={
        "company": "str. Company name, CNPJ, or ticker (via bridge). Empty = all.",
        "limit":   "int. Max results. Default: 20.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="dividends", mode="announcements", params=\'{"company":"PETR4"}\')',
    ],
)
def announcements(company: str = "", limit: int = 20) -> dict:
    """Official CVM IPE filings related to dividends.

    Searches IPE for events with keyword "dividendo" (case-insensitive) in the
    assunto (subject) field. Also accepts company filter.

    Delegates to data_sources.cvm.ipe.query_engine.query.
    """
    from data_sources.cvm.ipe.query_engine import query as ipe_query
    return ipe_query(company=company, keyword="dividendo", limit=limit)
