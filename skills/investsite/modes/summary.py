"""Mode: summary -- combined key indicators + latest Fato Relevante events.

Best-effort composition: if one sub-call fails, returns what's available.

Registered as "summary" in skills.investsite._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

[v1.1] Moved verbatim from the former skills/investsite/investsite.py
monolith. Internal calls to indicators() + events() now go to the sibling
mode files (aliased to avoid name clash with the summary mode name):
    from skills.investsite.modes.indicators import indicators as _indicators
    from skills.investsite.modes.events import events as _events
"""
from __future__ import annotations

from typing import Any

from skills.investsite._registry import register_mode
from skills.investsite.modes.indicators import indicators as _indicators
from skills.investsite.modes.events import events as _events


@register_mode(
    "summary",
    description=(
        "Combined: key indicators (prices, returns, balance, DRE TTM) + "
        "latest Fato Relevante events."
    ),
    include_in_all=False,
    params={
        "ticker": "str. Required.",
    },
    examples=[
        'skill(domain="investsite", mode="summary", params=\'{"ticker":"PETR4"}\')',
    ],
)
def summary(ticker: str = "") -> dict:
    """Combined: key indicators + latest events (Fato Relevante).

    Best-effort — if one section fails, returns what's available.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    result: dict[str, Any] = {"status": "ok", "ticker": ticker, "sections": {}}

    # 1. Key indicators
    try:
        ind = _indicators(ticker=ticker)
        if ind.get("status") == "ok":
            sections = ind.get("sections", {})
            result["sections"]["precos_relativos"] = sections.get("precos_relativos", {})
            result["sections"]["retornos_margens"] = sections.get("retornos_margens", {})
            result["sections"]["balanco_patrimonial"] = sections.get("balanco_patrimonial", {})
            result["sections"]["dre_ttm"] = sections.get("dre_ttm", {})
        else:
            result["sections"]["indicators"] = {"status": ind.get("status"),
                                                "error": ind.get("error", "")}
    except Exception as e:
        result["sections"]["indicators"] = {"status": "error", "error": str(e)}

    # 2. Latest Fato Relevante events
    try:
        evt = _events(ticker=ticker, categoria="Fato Relevante", limit=10)
        if evt.get("status") == "ok":
            result["sections"]["latest_events"] = {
                "count": evt.get("count", 0),
                "events": evt.get("events", []),
            }
        else:
            result["sections"]["latest_events"] = {"status": evt.get("status"),
                                                    "error": evt.get("error", "")}
    except Exception as e:
        result["sections"]["latest_events"] = {"status": "error", "error": str(e)}

    return result
