"""metrics/gross_margin.py -- Gross Margin fundamental ratio metric.

Gross Margin = TTM gross profit / TTM revenue
             = Lucro Bruto / Receita Líquida

Gross Margin is a FUNDAMENTAL RATIO -- it measures profitability at the
gross level (before operating expenses). Does NOT use price or shares
engines. Composes only gross_profit + revenue engines.

Engines composed: gross_profit + revenue

Interpretation:
  - Gross Margin > 40%: high (software, pharma, luxury)
  - Gross Margin 20-40%: typical (manufacturing, retail)
  - Gross Margin < 20%: low (commodities, supermarkets)
  - Gross Margin < 0%: company selling below cost

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.metrics.gross_margin import gross_margin_at, gross_margin_history
    g = gross_margin_at("PETR4", "2024-06-30")    # -> 0.35 (35%)
"""
from __future__ import annotations

from skills.cvm.historical.engines.gross_profit import gross_profit_at, gross_profit_periods
from skills.cvm.historical.engines.revenue import revenue_at, revenue_periods
from skills.cvm.historical._registry import MetricSpec, register_metric


# -- Ratio: Gross Margin = gross_profit / revenue ----------------------------

def gross_margin_at(company: str, date: str) -> float | None:
    """Compute Gross Margin at a specific date.

    Gross Margin = TTM gross profit / TTM revenue

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Gross Margin as a fraction (0.35 = 35%), or None if:
        - gross_profit is None or <= 0 (negative gross profit)
        - revenue is None or <= 0 (zero revenue)
    """
    gross_profit = gross_profit_at(company, date)
    if gross_profit is None or gross_profit <= 0:
        return None

    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None

    return gross_profit / revenue


# -- History: series with Gross Margin (no price, no shares) -----------------

def gross_margin_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute Gross Margin time series for a date range.

    Gross Margin changes only when gross_profit or revenue change (quarterly).
    No daily price driver -- series based on union of period dates.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "gross_margin", "ttm_gp", "ttm_rev"} sorted oldest-first.
    """
    gp_periods = gross_profit_periods(company)
    rev_periods = revenue_periods(company)

    all_dates = set()
    for gp in gp_periods:
        if date_from <= gp["date"] <= date_to:
            all_dates.add(gp["date"])
    for rp in rev_periods:
        if date_from <= rp["date"] <= date_to:
            all_dates.add(rp["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)

    result = []
    for date in sorted_dates:
        ttm_gp = None
        for gp in reversed(gp_periods):
            if gp["date"] <= date:
                ttm_gp = gp["ttm_gp"]
                break

        ttm_rev = None
        for rp in reversed(rev_periods):
            if rp["date"] <= date:
                ttm_rev = rp["ttm_rev"]
                break

        gross_margin = None
        if (ttm_gp is not None and ttm_gp > 0
            and ttm_rev is not None and ttm_rev > 0):
            gross_margin = ttm_gp / ttm_rev

        result.append({
            "date": date,
            "gross_margin": gross_margin,
            "ttm_gp": ttm_gp,
            "ttm_rev": ttm_rev,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="gross_margin",
    per_share_label=None,
    per_share_key=None,
    per_share_fn=None,
    ratio_label="Margem Bruta",
    ratio_key="gross_margin",
    ratio_fn=gross_margin_at,
    history_fn=gross_margin_history,
    engines=["gross_profit", "revenue"],
    aliases=["margem_bruta", "gm", "gross_margin_pct"],
))
