"""Mode: statements -- full financial statement (BPA/BPP/DRE/DFC/DVA/shares).

Fetches a financial statement page with % total computed columns.

Registered as "statements" in skills.investsite._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

[v1.1] Moved verbatim from the former skills/investsite/investsite.py
monolith.
"""
from __future__ import annotations

from skills.investsite._registry import register_mode
from skills.investsite.fetcher import fetch_page, url_statement
from skills.investsite.parsers import parse_statement


@register_mode(
    "statements",
    description=(
        "Full financial statement (BPA/BPP/DRE/DFC/DVA/shares) with "
        "% total columns."
    ),
    include_in_all=False,
    params={
        "ticker":     "str. Required.",
        "statement":  "str. BPA, BPP, DRE, DFC, DVA, shares. Default: DRE.",
    },
    examples=[
        'skill(domain="investsite", mode="statements", params=\'{"ticker":"PETR4","statement":"DRE"}\')',
    ],
)
def statements(ticker: str = "", statement: str = "DRE") -> dict:
    """Fetch a full financial statement page.

    Args:
        ticker: B3 ticker (PETR4).
        statement: One of: BPA, BPP, DRE, DFC, DVA, shares.

    Returns:
        Dict with account codes, descriptions, period values + % total columns.
        This is an alternative to data_sources/cvm/dfp — the added value is
        the % total computed columns.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    statement = statement.strip().upper()

    valid = ["BPA", "BPP", "DRE", "DFC", "DVA", "SHARES"]
    if statement not in valid:
        return {"status": "error",
                "error": f"Unknown statement '{statement}'. Available: {valid}"}

    try:
        url = url_statement(ticker, statement)
        html = fetch_page(url)
    except (ConnectionError, ValueError) as e:
        return {"status": "error", "error": str(e)}

    result = parse_statement(html, statement)
    result["ticker"] = ticker
    result["source"] = url
    return result
