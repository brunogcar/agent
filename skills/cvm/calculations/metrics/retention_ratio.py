"""metrics/retention_ratio.py -- Retention Ratio fundamental ratio metric.

Retention Ratio = 1 - Payout
                = 1 - (Dividends / Earnings)
                = 1 - (DPA TTM / Lucro Líquido TTM)

Measures the fraction of earnings retained by the company (not paid out as
dividends). The retained portion is reinvested in the business or used to
pay down debt. Together with ROE, it determines the Sustainable Growth
Rate (ROE × Retention = SGR).

Per task spec, "Payout = Dividends / Earnings" is computed by importing the
dividends and earnings engines directly (not via metrics.dpa.payout_at,
which would compose the shares engine for a per-share-correct LPA
denominator). The simplified form here is sufficient for relative
comparisons across periods and for the SGR composition.

Edge cases (per task spec):
  - earnings <= 0 (or None)        -> None (payout meaningless)
  - dividends is None or 0         -> 1.0 (100% retention; company pays nothing)
  - payout < 0 (negative dividends) -> None (rare, treat as data anomaly)
  - payout > 1 (overdistributing)   -> 0.0 (clamped to 0% retention)

Engines composed: dividends + earnings

Interpretation:
  - Retention = 1.0: company pays no dividends (100% reinvested)
  - Retention 0.5-0.8: balanced (mature companies with moderate dividends)
  - Retention < 0.3: company pays most earnings as dividends (low growth
    potential from retained earnings alone)
  - Retention = 0.0: company pays 100%+ of earnings as dividends
    (unsustainable -- either special dividend or慢慢 declining earnings)

Usage:
    from skills.cvm.calculations.metrics.retention_ratio import retention_ratio_at
    r = retention_ratio_at("PETR4", "2024-06-30")  # -> 0.58 (58% retained)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dividends import dividends_at, dividends_periods
from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def retention_ratio_at(company: str, date: str) -> float | None:
    """Retention Ratio = 1 - Payout where Payout = Dividends / Earnings.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Retention as a fraction (0.58 = 58% retained), or None if:
        - earnings is None or <= 0 (payout meaningless)
        - dividends is None and the company has no dividends data (we treat
          None dividends conservatively as "no dividends paid" -> retention
          = 1.0; this matches dpa_at's semantics where 0.0 means no
          dividends in the trailing year)
        - payout < 0 (negative dividends -- rare data anomaly)

        Clamped to 0.0 when payout > 1.0 (company distributing more than
        earned -- unsustainable; we report 0% retention rather than
        negative retention to keep downstream SGR computations clean).
    """
    earnings = ttm_earnings_at(company, date)
    if earnings is None or earnings <= 0:
        return None  # Negative/zero earnings -> payout meaningless

    dpa = dividends_at(company, date)
    # dividends_at returns None (no data) or a non-negative float (>= 0).
    # Treat both None and 0.0 as "no dividends paid" -> 100% retention.
    if dpa is None or dpa == 0:
        return 1.0

    payout = dpa / earnings
    if payout < 0:
        return None  # Negative payout (negative dividends) -> anomaly
    if payout > 1.0:
        return 0.0  # Overdistributing -> clamp to 0% retention

    return 1.0 - payout


def retention_ratio_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Retention Ratio time series -- union of dividends + earnings period dates."""
    dpa_periods_list = dividends_periods(company)
    earnings_periods_list = ttm_earnings_periods(company)

    all_dates = set()
    for periods in [dpa_periods_list, earnings_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        dpa = None
        for dp in reversed(dpa_periods_list):
            if dp["date"] <= date:
                dpa = dp["dpa"]
                break
        ttm = None
        for ep in reversed(earnings_periods_list):
            if ep["date"] <= date:
                ttm = ep["ttm"]
                break

        retention = None
        payout = None
        if ttm is not None and ttm > 0:
            if dpa is None or dpa == 0:
                retention = 1.0
                payout = 0.0
            else:
                p = dpa / ttm
                if p < 0:
                    retention = None
                    payout = None
                elif p > 1.0:
                    retention = 0.0
                    payout = p
                else:
                    retention = 1.0 - p
                    payout = p

        result.append({
            "date": date,
            "retention_ratio": retention,
            "payout": payout,
            "dpa": dpa,
            "ttm_earnings": ttm,
        })
    return result


register_metric(MetricSpec(
    name="retention_ratio",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Taxa de Retenção",
    ratio_key="retention_ratio",
    ratio_fn=retention_ratio_at,
    history_fn=retention_ratio_history,
    engines=["dividends", "earnings"],
    category="growth",
    aliases=["taxa_retencao", "retention", "rr"],
))
