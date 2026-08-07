"""metrics/gross_profit_growth.py -- Gross Profit growth metrics (3M, 1Y, 5Y).

Gross Profit Growth = (TTM Gross Profit now - TTM Gross Profit N periods ago) / |old|

Measures how fast the company's gross profit is growing across 3 time horizons.
Matches the private spreadsheet's "Resultado Bruto" growth row.

This file registers 3 separate metrics (one per horizon). Each uses the
shared growth_helpers module for the lookback logic.

Engines composed: gross_profit (TTM gross profit periods)

Usage:
    from skills.cvm.calculations.metrics.gross_profit_growth import (
        gross_profit_growth_3m_at, gross_profit_growth_1y_at, gross_profit_growth_5y_at,
    )
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.gross_profit import gross_profit_periods
from skills.cvm.calculations.growth_helpers import growth_at, growth_history
from skills.cvm.calculations._registry import MetricSpec, register_metric

_VALUE_KEY = "ttm_gp"


def _normalize_periods(company: str) -> list[dict]:
    """Fetch gross profit periods and normalize to {date, value} format for growth_helpers."""
    raw = gross_profit_periods(company)
    return [{"date": p["date"], "value": p.get(_VALUE_KEY)} for p in raw]


def gross_profit_growth_3m_at(company: str, date: str) -> float | None:
    """Gross profit growth over 3 months (90 days)."""
    periods = _normalize_periods(company)
    return growth_at(periods, date, 90)


def gross_profit_growth_3m_history(company: str, date_from: str, date_to: str) -> list[dict]:
    periods = _normalize_periods(company)
    result = growth_history(periods, 90, date_from, date_to)
    return [{**r, "gross_profit_growth_3m": r.get("growth")} for r in result]


def gross_profit_growth_1y_at(company: str, date: str) -> float | None:
    """Gross profit growth over 1 year (365 days)."""
    periods = _normalize_periods(company)
    return growth_at(periods, date, 365)


def gross_profit_growth_1y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    periods = _normalize_periods(company)
    result = growth_history(periods, 365, date_from, date_to)
    return [{**r, "gross_profit_growth_1y": r.get("growth")} for r in result]


def gross_profit_growth_5y_at(company: str, date: str) -> float | None:
    """Gross profit growth over 5 years (1825 days)."""
    periods = _normalize_periods(company)
    return growth_at(periods, date, 1825)


def gross_profit_growth_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    periods = _normalize_periods(company)
    result = growth_history(periods, 1825, date_from, date_to)
    return [{**r, "gross_profit_growth_5y": r.get("growth")} for r in result]


register_metric(MetricSpec(
    name="gross_profit_growth_3m",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Resultado Bruto 3M",
    ratio_key="gross_profit_growth_3m",
    ratio_fn=gross_profit_growth_3m_at,
    history_fn=gross_profit_growth_3m_history,
    engines=["gross_profit"],
    category="growth",
    aliases=["cresc_rb_3m", "crescimento_resultado_bruto_3m", "gp_growth_3m"],
    allow_negative=True,
    tooltip="Cresc. Resultado Bruto 3M = (Lucro Bruto TTM atual - há 3 meses) / |anterior|. Variação trimestral.",
))

register_metric(MetricSpec(
    name="gross_profit_growth_1y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Resultado Bruto 1A",
    ratio_key="gross_profit_growth_1y",
    ratio_fn=gross_profit_growth_1y_at,
    history_fn=gross_profit_growth_1y_history,
    engines=["gross_profit"],
    category="growth",
    aliases=["cresc_rb_1a", "crescimento_resultado_bruto_1ano", "gp_growth_1y"],
    allow_negative=True,
    tooltip="Cresc. Resultado Bruto 1A = (Lucro Bruto TTM atual - há 1 ano) / |anterior|. Variação anual.",
))

register_metric(MetricSpec(
    name="gross_profit_growth_5y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Crescimento Resultado Bruto 5A",
    ratio_key="gross_profit_growth_5y",
    ratio_fn=gross_profit_growth_5y_at,
    history_fn=gross_profit_growth_5y_history,
    engines=["gross_profit"],
    category="growth",
    aliases=["cresc_rb_5a", "crescimento_resultado_bruto_5anos", "gp_growth_5y"],
    allow_negative=True,
    tooltip="Cresc. Resultado Bruto 5A = (Lucro Bruto TTM atual - há 5 anos) / |anterior|. Variação quinquenal.",
))
