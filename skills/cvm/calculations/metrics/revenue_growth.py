"""metrics/revenue_growth.py -- Revenue growth metrics (3M, 1Y, 5Y).

Revenue Growth = (TTM Revenue now - TTM Revenue N periods ago) / |old|

Measures how fast the company's top line is growing across 3 time horizons:
  - 3M:  quarter-over-quarter TTM change (90 days back)
  - 1Y:  year-over-year (365 days back)
  - 5Y:  5-year growth (1825 days back)

Inspired by the StatusInvest spreadsheet's "CRESCIMENTO" section which shows
3 Meses / 1 Ano / 5 Anos growth for Receita Líquida, Resultado Bruto, and
Lucro Líquido.

This file registers 3 separate metrics (one per horizon). Each uses the
shared growth_helpers module for the lookback logic.

Engines composed: revenue (TTM revenue periods)

Interpretation:
  - Growth > 0.15 (15%): strong growth
  - Growth 0.05-0.15: moderate growth
  - Growth 0-0.05: slow growth
  - Growth < 0: declining revenue

Usage:
    from skills.cvm.calculations.metrics.revenue_growth import (
        revenue_growth_3m_at, revenue_growth_1y_at, revenue_growth_5y_at,
    )
    g3 = revenue_growth_3m_at("PETR4", "2024-06-30")  # -> 0.0383 (3.83%)
    g1 = revenue_growth_1y_at("PETR4", "2024-06-30")  # -> 0.0206 (2.06%)
    g5 = revenue_growth_5y_at("PETR4", "2024-06-30")  # -> 0.15 (15%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.revenue import revenue_periods
from skills.cvm.calculations.growth_helpers import growth_at, growth_history
from skills.cvm.calculations._registry import MetricSpec, register_metric

_VALUE_KEY = "ttm_rev"


# ── 3-month growth (QoQ TTM change) ──────────────────────────────────────────

def revenue_growth_3m_at(company: str, date: str) -> float | None:
    """Revenue growth over 3 months (90 days).

    Compares TTM revenue at `date` vs TTM revenue 90 days earlier.
    Returns growth as a fraction (0.05 = 5%), or None if data is missing.
    """
    return growth_at(company, date, revenue_periods, _VALUE_KEY, 90)


def revenue_growth_3m_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Revenue 3M growth time series."""
    return growth_history(company, date_from, date_to,
                          revenue_periods, _VALUE_KEY, 90, "revenue_growth_3m")


# ── 1-year growth (YoY) ──────────────────────────────────────────────────────

def revenue_growth_1y_at(company: str, date: str) -> float | None:
    """Revenue growth over 1 year (365 days).

    Compares TTM revenue at `date` vs TTM revenue 365 days earlier.
    Returns growth as a fraction (0.05 = 5%), or None if data is missing.
    """
    return growth_at(company, date, revenue_periods, _VALUE_KEY, 365)


def revenue_growth_1y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Revenue 1Y growth time series."""
    return growth_history(company, date_from, date_to,
                          revenue_periods, _VALUE_KEY, 365, "revenue_growth_1y")


# ── 5-year growth ────────────────────────────────────────────────────────────

def revenue_growth_5y_at(company: str, date: str) -> float | None:
    """Revenue growth over 5 years (1825 days).

    Compares TTM revenue at `date` vs TTM revenue 5 years earlier.
    Returns growth as a fraction (1.0 = 100% growth), or None if data is missing.
    """
    return growth_at(company, date, revenue_periods, _VALUE_KEY, 1825)


def revenue_growth_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Revenue 5Y growth time series."""
    return growth_history(company, date_from, date_to,
                          revenue_periods, _VALUE_KEY, 1825, "revenue_growth_5y")


# ── Register 3 metrics ───────────────────────────────────────────────────────

register_metric(MetricSpec(
    name="revenue_growth_3m",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Receita 3M",
    ratio_key="revenue_growth_3m",
    ratio_fn=revenue_growth_3m_at,
    history_fn=revenue_growth_3m_history,
    engines=["revenue"],
    category="growth",
    aliases=["cresc_receita_3m", "crescimento_receita_3m", "rev_growth_3m"],
))

register_metric(MetricSpec(
    name="revenue_growth_1y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Receita 1A",
    ratio_key="revenue_growth_1y",
    ratio_fn=revenue_growth_1y_at,
    history_fn=revenue_growth_1y_history,
    engines=["revenue"],
    category="growth",
    aliases=["cresc_receita_1a", "crescimento_receita_1ano", "rev_growth_1y"],
))

register_metric(MetricSpec(
    name="revenue_growth_5y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Receita 5A",
    ratio_key="revenue_growth_5y",
    ratio_fn=revenue_growth_5y_at,
    history_fn=revenue_growth_5y_history,
    engines=["revenue"],
    category="growth",
    aliases=["cresc_receita_5a", "crescimento_receita_5anos", "rev_growth_5y"],
))
