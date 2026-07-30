"""Mode: side_by_side -- compare N tickers across 3 sections (default mode).

Calls the existing financials + valuation + dividends skills internally per
ticker (best-effort — a ticker missing from one source doesn't fail the whole
comparison) and merges into a side-by-side structure.

Sections produced (returned as a dict keyed by name):
  - valuation:  valuation.ratios() metrics (price, P/L, EV/EBITDA, ROE, ...)
  - financials: financials.summary() latest_annual metrics + ratios
                (Receita, EBITDA, Lucro Líquido, margins, ROE, ...)
  - dividends:  dividends.summary() extracted metrics (event count, B3 DPA,
                annual dividendos/jcp/total)

Each section: rows = tickers, columns = metrics.

Registered as "side_by_side" in skills.cvm.comparison._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.comparison._registry import register_mode
from skills.cvm.comparison.helpers import _VALUATION_COLS, _FINANCIALS_COLS, _DIVIDENDS_COLS
from skills.cvm.comparison.fetchers import _fetch_all, _fetch_sectors, _build_section


@register_mode(
    "side_by_side",
    description=(
        "3 sections — Valuation Ratios, Financial Metrics (latest annual), "
        "Dividend Metrics. Each section: rows = tickers, columns = metrics."
    ),
    params={
        "tickers":     "list[str]. B3 tickers, e.g. [\"PETR4\",\"VALE3\"]. Required (min 2).",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="comparison", mode="side_by_side", params=\'{"tickers":["PETR4","VALE3","ITUB4"]}\')',
        'skill(domain="cvm", sub_domain="comparison", mode="side_by_side", params=\'{"tickers":["SUZB3","KLBN11"]}\')',
    ],
)
def side_by_side(tickers: list = None, consolidado: int = 1) -> dict:
    """Compare N tickers across 3 sections (valuation, financials, dividends).

    Args:
        tickers: List of B3 tickers, e.g. ["PETR4","VALE3"]. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    per_ticker = _fetch_all(tickers, consolidado)

    # [v1.2] Sector tagging — resolve each ticker's sector from CAD
    sectors = _fetch_sectors(tickers)

    sections = {
        "valuation":   _build_section("Valuation Ratios", _VALUATION_COLS,
                                      [t["valuation"] for t in per_ticker], tickers),
        "financials":  _build_section("Financial Metrics (latest annual)", _FINANCIALS_COLS,
                                      [t["financials"] for t in per_ticker], tickers),
        "dividends":   _build_section("Dividend Metrics", _DIVIDENDS_COLS,
                                      [t["dividends"] for t in per_ticker], tickers),
    }

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": sections,
        "errors": [t["error"] for t in per_ticker if t["error"]],
    }
