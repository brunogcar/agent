"""skills/investsite/__init__.py -- Investsite skill manifest + router.

Fetches financial data from investsite.com.br (per-ticker pages).

Unlike CVM/B3 skills which read from local databases, this skill fetches
live data from the web. No sync, no local DB — each call hits the site.

5 modes:
  indicators (default) — main page: 10 tables (prices, DRE, returns, balance, cashflow)
  statements          — full financial statement (BPA/BPP/DRE/DFC/DVA) with % total
  events              — periodic info by category with CVM PDF links
  summary             — combined: key indicators + latest events
  listing             — list available event categories
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "domain":       "investsite",
    "description":  (
        "Financial data from investsite.com.br (live web scraping). "
        "Per-ticker indicators, full statements, periodic events with CVM links. "
        "No local DB — fetches live each call."
    ),
    "has_sub_domains": False,
    "source":  "investsite.com.br (live HTTP)",
    "storage": "in-memory cache only (1h TTL)",
    "modes": {
        "indicators": {
            "description": "Main page: 10 tables (dados básicos, preços relativos, DRE TTM/quarterly, retornos, balanço, fluxo de caixa, experimental).",
            "include_in_all": True,
            "params": {
                "ticker": "str. B3 ticker (PETR4). Required.",
            },
            "examples": [
                'skill(domain="investsite", mode="indicators", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "statements": {
            "description": "Full financial statement (BPA/BPP/DRE/DFC/DVA/shares) with % total columns.",
            "include_in_all": False,
            "params": {
                "ticker":     "str. Required.",
                "statement":  "str. BPA, BPP, DRE, DFC, DVA, shares. Default: DRE.",
            },
            "examples": [
                'skill(domain="investsite", mode="statements", params=\'{"ticker":"PETR4","statement":"DRE"}\')',
            ],
        },
        "events": {
            "description": "Periodic info (IPE) by category with direct CVM rad.cvm.gov.br PDF links.",
            "include_in_all": False,
            "params": {
                "ticker":    "str. Required.",
                "categoria": "str. Filter: Fato Relevante, Comunicado ao Mercado, etc. Empty = all.",
                "limit":     "int. Max events. Default: 20.",
            },
            "examples": [
                'skill(domain="investsite", mode="events", params=\'{"ticker":"PETR4","categoria":"Fato Relevante"}\')',
            ],
        },
        "summary": {
            "description": "Combined: key indicators (prices, returns, balance, DRE TTM) + latest Fato Relevante events.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Required.",
            },
            "examples": [
                'skill(domain="investsite", mode="summary", params=\'{"ticker":"PETR4"}\')',
            ],
        },
        "listing": {
            "description": "List available event categories.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Optional (for reference).",
            },
            "examples": [
                'skill(domain="investsite", mode="listing")',
            ],
        },
    },
}


def route(sub_domain: str = "", mode: str = "", **kwargs) -> dict:
    """Dispatch investsite mode call.

    Note: investsite is a flat domain (no sub-domains). The sub_domain param
    is accepted for dispatcher compatibility but ignored.
    """
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.investsite.investsite import (
        indicators, statements, events, summary, listing,
    )

    dispatch = {
        "indicators": indicators,
        "statements": statements,
        "events": events,
        "summary": summary,
        "listing": listing,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "domain": "investsite",
                "mode": mode, "error": str(e)}
