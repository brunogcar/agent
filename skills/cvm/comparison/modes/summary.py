"""Mode: summary -- single quick-compare table (10 KPIs).

Calls financials + valuation + dividends per ticker (best-effort) and merges
the 3 metric dicts into a single row per ticker. Returns a single section
with ~10 KPI columns:
  Preço, Market Cap, P/L, P/VPA, EV/EBITDA, ROE, Div Yield,
  Receita Líquida, EBITDA, Lucro Líquido.

Registered as "summary" in skills.cvm.comparison._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.comparison._registry import register_mode
from skills.cvm.comparison.helpers import _SUMMARY_COLS
from skills.cvm.comparison.fetchers import _fetch_all, _fetch_sectors, _build_section


@register_mode(
    "summary",
    description=(
        "Single quick-compare table: 1 row per ticker, ~10 KPI columns "
        "(Preço, Market Cap, P/L, P/VPA, EV/EBITDA, ROE, Div Yield, Receita, "
        "EBITDA, Lucro Líquido)."
    ),
    params={
        "tickers":     "list[str]. Required (min 2).",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="cvm", sub_domain="comparison", mode="summary", params=\'{"tickers":["SUZB3","KLBN11"]}\')',
    ],
)
def summary(tickers: list = None, consolidado: int = 1) -> dict:
    """Single quick-compare table: 1 row per ticker, ~10 KPI columns.

    Args:
        tickers: List of B3 tickers. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    per_ticker = _fetch_all(tickers, consolidado)

    # Merge valuation + financials ratios into a single row per ticker
    merged = []
    for t in per_ticker:
        row = dict(t["valuation"])          # price, p_l, market_cap, ...
        row.update(t["financials"])         # receita, ebitda, roe, ...
        row.update(t["dividends"])          # dividend_yield (from valuation), event_count, ...
        merged.append(row)

    section = _build_section("Quick Compare", _SUMMARY_COLS, merged, tickers)

    # [v1.2] Sector tagging
    sectors = _fetch_sectors(tickers)

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": [section],
        "errors": [t["error"] for t in per_ticker if t["error"]],
    }
