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

from skills.cvm.calculations.engines.gross_profit import gross_profit_periods
from skills.cvm.calculations.growth_helpers import growth_at, growth_history
from skills.cvm.calculations._registry import MetricSpec, register_metric

_VALUE_KEY = "ttm_gp"


def gross_profit_growth_3m_at(company: str, date: str) -> float | None:
    """Gross profit growth over 3 months (90 days)."""
    return growth_at(company, date, gross_profit_periods, _VALUE_KEY, 90)


def gross_profit_growth_3m_history(company: str, date_from: str, date_to: str) -> list[dict]:
    return growth_history(company, date_from, date_to,
                          gross_profit_periods, _VALUE_KEY, 90, "gross_profit_growth_3m")


def gross_profit_growth_1y_at(company: str, date: str) -> float | None:
    """Gross profit growth over 1 year (365 days)."""
    return growth_at(company, date, gross_profit_periods, _VALUE_KEY, 365)


def gross_profit_growth_1y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    return growth_history(company, date_from, date_to,
                          gross_profit_periods, _VALUE_KEY, 365, "gross_profit_growth_1y")


def gross_profit_growth_5y_at(company: str, date: str) -> float | None:
    """Gross profit growth over 5 years (1825 days)."""
    return growth_at(company, date, gross_profit_periods, _VALUE_KEY, 1825)


def gross_profit_growth_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    return growth_history(company, date_from, date_to,
                          gross_profit_periods, _VALUE_KEY, 1825, "gross_profit_growth_5y")


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
))
