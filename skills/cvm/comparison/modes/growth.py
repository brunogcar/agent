"""Mode: growth -- QoQ + YoY % change + TTM ratios for N tickers.

Calls financials.quarterly(periods=8) per ticker to get standalone quarters,
then computes QoQ (latest vs prior) and YoY (latest vs same quarter prior
year) growth for Receita, EBITDA, Lucro Líquido. Also includes TTM
Marg. EBITDA and ROE from the financials skill's TTM summary.

Growth math lives in skills.cvm.comparison.helpers (_compute_growth +
_pct_change). This module just orchestrates the fetch + section assembly.

Registered as "growth" in skills.cvm.comparison._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.comparison._registry import register_mode
from skills.cvm.comparison.helpers import _GROWTH_COLS, _compute_growth
from skills.cvm.comparison.fetchers import _fetch_sectors, _build_section


@register_mode(
    "growth",
    description=(
        "Growth metrics: QoQ + YoY % change for Receita, EBITDA, Lucro "
        "Líquido + TTM Marg. EBITDA + ROE. Calls financials.quarterly("
        "periods=8) per ticker."
    ),
    params={
        "tickers":     "list[str]. Required (min 2).",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="comparison", mode="growth", params=\'{"tickers":["SUZB3","KLBN11"]}\')',
    ],
)
def growth(tickers: list = None, consolidado: int = 1) -> dict:
    """Compare N tickers on growth metrics: QoQ + YoY % change + TTM ratios.

    Calls financials.quarterly(periods=8) per ticker to get standalone quarters,
    then computes QoQ (latest vs prior) and YoY (latest vs same quarter prior
    year) growth for Receita, EBITDA, Lucro Líquido. Also includes TTM
    Marg. EBITDA and ROE from the financials skill's TTM summary.

    Args:
        tickers: List of B3 tickers. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    from skills.cvm.financials.modes.quarterly import quarterly as fin_quarterly

    growth_data = []
    errors = []
    for ticker in tickers:
        try:
            r = fin_quarterly(company=ticker, periods=8, consolidado=consolidado)
            if r.get("status") == "ok":
                growth_data.append(_compute_growth(r))
            else:
                growth_data.append({})
                errors.append(f"{ticker}: financials: {r.get('error', r.get('status', ''))}")
        except Exception as e:
            growth_data.append({})
            errors.append(f"{ticker}: financials: {e}")

    section = _build_section("Growth Metrics (QoQ + YoY + TTM)", _GROWTH_COLS,
                             growth_data, tickers)

    # [v1.2] Sector tagging
    sectors = _fetch_sectors(tickers)

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": [section],
        "errors": errors,
    }
