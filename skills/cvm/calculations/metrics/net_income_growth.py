"""metrics/net_income_growth.py -- Net Income growth metrics (3M, 1Y, 5Y).

Net Income Growth = (TTM Earnings now - TTM Earnings N periods ago) / |old|

Measures how fast the company's bottom line is growing across 3 time horizons.
Matches the private spreadsheet's "Lucro Líquido" growth row.

Uses the earnings engine (TTM earnings = TTM net income / lucro líquido).

This file registers 3 separate metrics (one per horizon). Each uses the
shared growth_helpers module for the lookback logic.

Engines composed: earnings (TTM earnings periods)

Usage:
    from skills.cvm.calculations.metrics.net_income_growth import (
        net_income_growth_3m_at, net_income_growth_1y_at, net_income_growth_5y_at,
    )
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_periods
from skills.cvm.calculations.growth_helpers import growth_at, growth_history
from skills.cvm.calculations._registry import MetricSpec, register_metric

_VALUE_KEY = "ttm"


def _normalize_periods(company: str) -> list[dict]:
    """Fetch earnings periods and normalize to {date, value} format for growth_helpers."""
    raw = ttm_earnings_periods(company)
    return [{"date": p["date"], "value": p.get(_VALUE_KEY)} for p in raw]


def net_income_growth_3m_at(company: str, date: str) -> float | None:
    """Net income growth over 3 months (90 days)."""
    periods = _normalize_periods(company)
    return growth_at(periods, date, 90)


def net_income_growth_3m_history(company: str, date_from: str, date_to: str) -> list[dict]:
    periods = _normalize_periods(company)
    result = growth_history(periods, 90, date_from, date_to)
    return [{**r, "net_income_growth_3m": r.get("growth")} for r in result]


def net_income_growth_1y_at(company: str, date: str) -> float | None:
    """Net income growth over 1 year (365 days)."""
    periods = _normalize_periods(company)
    return growth_at(periods, date, 365)


def net_income_growth_1y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    periods = _normalize_periods(company)
    result = growth_history(periods, 365, date_from, date_to)
    return [{**r, "net_income_growth_1y": r.get("growth")} for r in result]


def net_income_growth_5y_at(company: str, date: str) -> float | None:
    """Net income growth over 5 years (1825 days)."""
    periods = _normalize_periods(company)
    return growth_at(periods, date, 1825)


def net_income_growth_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    periods = _normalize_periods(company)
    result = growth_history(periods, 1825, date_from, date_to)
    return [{**r, "net_income_growth_5y": r.get("growth")} for r in result]


register_metric(MetricSpec(
    name="net_income_growth_3m",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Lucro Líquido 3M",
    ratio_key="net_income_growth_3m",
    ratio_fn=net_income_growth_3m_at,
    history_fn=net_income_growth_3m_history,
    engines=["earnings"],
    category="growth",
    aliases=["cresc_ll_3m", "crescimento_lucro_liquido_3m", "ni_growth_3m"],
    allow_negative=True,
    tooltip="Cresc. Lucro 3M = (Lucro TTM atual - Lucro TTM há 3 meses) / |anterior|. Variação trimestral do lucro.",
))

register_metric(MetricSpec(
    name="net_income_growth_1y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Lucro Líquido 1A",
    ratio_key="net_income_growth_1y",
    ratio_fn=net_income_growth_1y_at,
    history_fn=net_income_growth_1y_history,
    engines=["earnings"],
    category="growth",
    aliases=["cresc_ll_1a", "crescimento_lucro_liquido_1ano", "ni_growth_1y"],
    allow_negative=True,
    tooltip="Cresc. Lucro 1A = (Lucro TTM atual - Lucro TTM há 1 ano) / |anterior|. Variação anual do lucro.",
))

register_metric(MetricSpec(
    name="net_income_growth_5y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Lucro Líquido 5A",
    ratio_key="net_income_growth_5y",
    ratio_fn=net_income_growth_5y_at,
    history_fn=net_income_growth_5y_history,
    engines=["earnings"],
    category="growth",
    aliases=["cresc_ll_5a", "crescimento_lucro_liquido_5anos", "ni_growth_5y"],
    allow_negative=True,
    tooltip="Cresc. Lucro 5A = (Lucro TTM atual - Lucro TTM há 5 anos) / |anterior|. Variação quinquenal do lucro.",
))
