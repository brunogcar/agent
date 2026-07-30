"""Mode: events -- periodic info (IPE) by category with CVM PDF links.

Registered as "events" in skills.investsite._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

[v1.1] Moved verbatim from the former skills/investsite/investsite.py
monolith.
"""
from __future__ import annotations

from skills.investsite._registry import register_mode
from skills.investsite.fetcher import fetch_page, url_events
from skills.investsite.parsers import parse_events


@register_mode(
    "events",
    description=(
        "Periodic info (IPE) by category with direct CVM rad.cvm.gov.br "
        "PDF links."
    ),
    include_in_all=False,
    params={
        "ticker":    "str. Required.",
        "categoria": "str. Filter: Fato Relevante, Comunicado ao Mercado, etc. Empty = all.",
        "limit":     "int. Max events. Default: 20.",
    },
    examples=[
        'skill(domain="investsite", mode="events", params=\'{"ticker":"PETR4","categoria":"Fato Relevante"}\')',
    ],
)
def events(ticker: str = "", categoria: str = "", limit: int = 20) -> dict:
    """Fetch periodic info (IPE) by category from investsite.

    Returns events with direct CVM rad.cvm.gov.br PDF links.

    Args:
        ticker: B3 ticker (PETR4).
        categoria: Category filter. Empty = all. Available:
            Assembleia, Aviso aos Acionistas, Comunicado ao Mercado,
            Dados Econômico-Financeiros, Fato Relevante, Relatório Proventos,
            Reunião da Administração.
        limit: Max events to return. Default: 20.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()

    try:
        url = url_events(ticker, categoria)
        html = fetch_page(url)
    except ConnectionError as e:
        return {"status": "error", "error": str(e)}

    result = parse_events(html, categoria)
    result["ticker"] = ticker
    result["source"] = url

    if limit and result.get("events"):
        result["events"] = result["events"][:limit]
        result["count"] = len(result["events"])

    return result
