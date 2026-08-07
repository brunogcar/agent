"""metrics/sustainable_growth.py -- Sustainable Growth Rate fundamental metric.

Sustainable Growth Rate (SGR) = ROE × Retention Ratio
                              = (Lucro Líquido / PL) × (1 - Payout)

Measures the maximum growth rate a company can sustain from internally
generated funds (retained earnings) without raising external equity or
increasing financial leverage. If a company grows faster than its SGR,
it must either issue new equity, increase debt, or reduce dividends.

Composed from two existing metrics (option (a) per task spec):
  - ROE              from metrics.roe.roe_at            (engines: earnings + pl)
  - Retention Ratio  from metrics.retention_ratio.retention_ratio_at
                                                       (engines: dividends + earnings)

Transitively composes three engines: earnings + pl + dividends (earnings
shared by both). The engines= list below lists these ENGINES (not the
metrics composed) per task spec.

Engines composed: earnings + pl + dividends

Interpretation:
  - SGR > 15%:   high sustainable growth potential (rare; high ROE + high
    retention)
  - SGR 5-15%:   healthy (typical for quality compounders)
  - SGR 0-5%:    modest (mature companies paying most earnings as dividends)
  - SGR = 0:     company pays 100% of earnings as dividends (no internal
    growth funding)
  - SGR = None:  when ROE is None (negative earnings or equity) or
    Retention is None (negative earnings -- payout meaningless)

Usage:
    from skills.cvm.calculations.metrics.sustainable_growth import sustainable_growth_at
    s = sustainable_growth_at("PETR4", "2024-06-30")  # -> 0.085 (8.5%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_periods
from skills.cvm.calculations.engines.bpp.pl import pl_periods
from skills.cvm.calculations.engines.dividends import dividends_periods
from skills.cvm.calculations.metrics.roe import roe_at
from skills.cvm.calculations.metrics.retention_ratio import retention_ratio_at
from skills.cvm.calculations._registry import MetricSpec, register_metric


def sustainable_growth_at(company: str, date: str) -> float | None:
    """Sustainable Growth Rate = ROE × Retention Ratio.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        SGR as a fraction (0.085 = 8.5%), or None if either ROE or
        Retention is None, or if ROE <= 0 (no sustainable growth from
        internal funds when losing money or breaking even), or if
        Retention < 0 (defensive -- retention_ratio_at already clamps
        negative payouts to None, but we guard again here for safety).
    """
    roe = roe_at(company, date)
    if roe is None or roe <= 0:
        return None  # ROE <= 0 -> no sustainable internal growth

    retention = retention_ratio_at(company, date)
    if retention is None or retention < 0:
        return None  # Retention < 0 (shouldn't happen, but defensive)

    return roe * retention


def sustainable_growth_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Sustainable Growth Rate time series -- union of earnings + pl + dividends
    period dates (the three engines composed transitively).
    """
    earnings_periods_list = ttm_earnings_periods(company)
    pl_periods_list = pl_periods(company)
    dpa_periods_list = dividends_periods(company)

    all_dates = set()
    for periods in [earnings_periods_list, pl_periods_list, dpa_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        roe = roe_at(company, date)
        retention = retention_ratio_at(company, date)

        sgr = None
        if (roe is not None and roe > 0
            and retention is not None and retention >= 0):
            sgr = roe * retention

        result.append({
            "date": date,
            "sustainable_growth": sgr,
            "roe": roe,
            "retention_ratio": retention,
        })
    return result


register_metric(MetricSpec(
    name="sustainable_growth",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Sustentável",
    ratio_key="sustainable_growth",
    ratio_fn=sustainable_growth_at,
    history_fn=sustainable_growth_history,
    engines=["earnings", "pl", "dividends"],
    category="growth",
    aliases=["crescimento_sustentavel", "sgr", "gs"],
))
