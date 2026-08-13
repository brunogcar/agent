"""metrics/cagr.py -- CAGR (Compound Annual Growth Rate) metrics.

CAGR = (V_end / V_start)^(1/n) - 1

Unlike the existing revenue_growth_* metrics which compute SIMPLE growth
((current - prior) / |prior|), CAGR gives the ANNUALIZED compound rate —
the constant yearly rate that would take V_start to V_end over n years.

Example:
  Revenue 2020: 100B
  Revenue 2025: 200B
  Simple growth (5Y) = (200 - 100) / 100 = 100% (total over 5Y)
  CAGR (5Y) = (200/100)^(1/5) - 1 = 0.1487 = 14.87% per year

CAGR is more useful for comparing growth across different time windows
because it normalizes to a per-year rate.

Metrics registered (6 total):
  - revenue_cagr_3y, revenue_cagr_5y
  - earnings_cagr_3y, earnings_cagr_5y
  - gross_profit_cagr_3y, gross_profit_cagr_5y

Engines composed: revenue, ttm_earnings, gross_profit (each provides
*_periods() for the historical lookback)

Usage:
    from skills.cvm.calculations.metrics.cagr import revenue_cagr_5y_at
    r = revenue_cagr_5y_at("PETR4", "2024-06-30")  # -> 0.1487 (= 14.87%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.dre.gross_profit import gross_profit_at, gross_profit_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def _cagr_at(periods: list[dict], target_date: str, lookback_days: int) -> float | None:
    """Compute CAGR at target_date over a lookback window.

    CAGR = (V_end / V_start)^(365/lookback_days) - 1

    - V_end   = the most recent period on or before target_date with non-None value.
    - V_start = the period closest to (target_date - lookback_days) with
                non-None, non-zero, positive value.

    Returns None if either endpoint is unavailable, if V_start <= 0,
    or if V_end <= 0 (CAGR undefined for negative/zero endpoints).

    Args:
        periods: List of {"date": str, "<key>": float} sorted oldest-first.
        target_date: YYYY-MM-DD.
        lookback_days: 1095 for 3Y, 1825 for 5Y.
    """
    from datetime import date as _date, timedelta as _timedelta

    try:
        target = _date.fromisoformat(target_date)
    except (ValueError, TypeError):
        return None

    # Find V_end: most recent period <= target_date with non-None value
    v_end = None
    end_date = None
    for p in reversed(periods):
        try:
            p_date = _date.fromisoformat(p["date"])
        except (ValueError, KeyError, TypeError):
            continue
        if p_date <= target:
            # Get the value from whichever key holds the data
            # [v1.25 fix] Added ttm_rev (revenue_periods) + ttm_gp (gross_profit_periods)
            val = p.get("value") or p.get("revenue") or p.get("ttm") or p.get("gross_profit") or p.get("ttm_rev") or p.get("ttm_gp")
            if val is not None and val > 0:
                v_end = float(val)
                end_date = p_date
                break

    if v_end is None or v_end <= 0:
        return None

    # Find V_start: closest period to (target - lookback_days)
    target_start = target - _timedelta(days=lookback_days)
    v_start = None
    start_date = None
    best_diff = None
    for p in periods:
        try:
            p_date = _date.fromisoformat(p["date"])
        except (ValueError, KeyError, TypeError):
            continue
        if p_date > target:
            break
        val = p.get("value") or p.get("revenue") or p.get("ttm") or p.get("gross_profit") or p.get("ttm_rev") or p.get("ttm_gp")
        if val is not None and val > 0:
            diff = abs((p_date - target_start).days)
            if best_diff is None or diff < best_diff:
                # Only accept if within 1.5x lookback window
                if diff <= lookback_days * 1.5:
                    best_diff = diff
                    v_start = float(val)
                    start_date = p_date

    if v_start is None or v_start <= 0:
        return None

    # Compute actual years between start and end
    if end_date is None or start_date is None:
        return None
    actual_days = (end_date - start_date).days
    if actual_days <= 0:
        return None

    years = actual_days / 365.0
    if years < 0.5:  # Need at least 6 months of data
        return None

    # CAGR = (V_end / V_start)^(1/years) - 1
    ratio = v_end / v_start
    if ratio <= 0:
        return None

    cagr = ratio ** (1.0 / years) - 1.0
    return cagr


# ── Revenue CAGR ──────────────────────────────────────────────────────────────

def revenue_cagr_3y_at(company: str, date: str) -> float | None:
    """Revenue CAGR over 3 years."""
    periods = revenue_periods(company)
    return _cagr_at(periods, date, 1095)


def revenue_cagr_5y_at(company: str, date: str) -> float | None:
    """Revenue CAGR over 5 years."""
    periods = revenue_periods(company)
    return _cagr_at(periods, date, 1825)


def revenue_cagr_3y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Revenue 3Y CAGR time series."""
    periods = revenue_periods(company)
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), 1095)
        result.append({"date": current.isoformat(), "revenue_cagr_3y": val})
        current += _timedelta(days=90)  # Quarterly sampling
    return result


def revenue_cagr_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Revenue 5Y CAGR time series."""
    periods = revenue_periods(company)
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), 1825)
        result.append({"date": current.isoformat(), "revenue_cagr_5y": val})
        current += _timedelta(days=90)
    return result


# ── Earnings CAGR ─────────────────────────────────────────────────────────────

def earnings_cagr_3y_at(company: str, date: str) -> float | None:
    """Earnings (net income) CAGR over 3 years."""
    periods = ttm_earnings_periods(company)
    return _cagr_at(periods, date, 1095)


def earnings_cagr_5y_at(company: str, date: str) -> float | None:
    """Earnings (net income) CAGR over 5 years."""
    periods = ttm_earnings_periods(company)
    return _cagr_at(periods, date, 1825)


def earnings_cagr_3y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Earnings 3Y CAGR time series."""
    periods = ttm_earnings_periods(company)
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), 1095)
        result.append({"date": current.isoformat(), "earnings_cagr_3y": val})
        current += _timedelta(days=90)
    return result


def earnings_cagr_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Earnings 5Y CAGR time series."""
    periods = ttm_earnings_periods(company)
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), 1825)
        result.append({"date": current.isoformat(), "earnings_cagr_5y": val})
        current += _timedelta(days=90)
    return result


# ── Gross Profit CAGR ─────────────────────────────────────────────────────────

def gross_profit_cagr_3y_at(company: str, date: str) -> float | None:
    """Gross profit CAGR over 3 years."""
    periods = gross_profit_periods(company)
    return _cagr_at(periods, date, 1095)


def gross_profit_cagr_5y_at(company: str, date: str) -> float | None:
    """Gross profit CAGR over 5 years."""
    periods = gross_profit_periods(company)
    return _cagr_at(periods, date, 1825)


def gross_profit_cagr_3y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Gross profit 3Y CAGR time series."""
    periods = gross_profit_periods(company)
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), 1095)
        result.append({"date": current.isoformat(), "gross_profit_cagr_3y": val})
        current += _timedelta(days=90)
    return result


def gross_profit_cagr_5y_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Gross profit 5Y CAGR time series."""
    periods = gross_profit_periods(company)
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), 1825)
        result.append({"date": current.isoformat(), "gross_profit_cagr_5y": val})
        current += _timedelta(days=90)
    return result


# ── Register 6 CAGR metrics ───────────────────────────────────────────────────

register_metric(MetricSpec(
    name="revenue_cagr_3y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CAGR Receita 3A",
    ratio_key="revenue_cagr_3y",
    ratio_fn=revenue_cagr_3y_at,
    history_fn=revenue_cagr_3y_history,
    engines=["revenue"],
    category="growth",
    aliases=["cagr_receita_3a", "cagr_revenue_3y"],
    allow_negative=True,
    tooltip="CAGR Receita 3A = (Receita_atual / Receita_3A_atrás)^(1/3) - 1. Crescimento anualizado composto.",
))

register_metric(MetricSpec(
    name="revenue_cagr_5y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CAGR Receita 5A",
    ratio_key="revenue_cagr_5y",
    ratio_fn=revenue_cagr_5y_at,
    history_fn=revenue_cagr_5y_history,
    engines=["revenue"],
    category="growth",
    aliases=["cagr_receita_5a", "cagr_revenue_5y"],
    allow_negative=True,
    tooltip="CAGR Receita 5A = (Receita_atual / Receita_5A_atrás)^(1/5) - 1. Crescimento anualizado composto.",
))

register_metric(MetricSpec(
    name="earnings_cagr_3y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CAGR Lucro 3A",
    ratio_key="earnings_cagr_3y",
    ratio_fn=earnings_cagr_3y_at,
    history_fn=earnings_cagr_3y_history,
    engines=["earnings"],
    category="growth",
    aliases=["cagr_lucro_3a", "cagr_earnings_3y"],
    allow_negative=True,
    tooltip="CAGR Lucro 3A = (Lucro_atual / Lucro_3A_atrás)^(1/3) - 1. Crescimento anualizado composto.",
))

register_metric(MetricSpec(
    name="earnings_cagr_5y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CAGR Lucro 5A",
    ratio_key="earnings_cagr_5y",
    ratio_fn=earnings_cagr_5y_at,
    history_fn=earnings_cagr_5y_history,
    engines=["earnings"],
    category="growth",
    aliases=["cagr_lucro_5a", "cagr_earnings_5y"],
    allow_negative=True,
    tooltip="CAGR Lucro 5A = (Lucro_atual / Lucro_5A_atrás)^(1/5) - 1. Crescimento anualizado composto.",
))

register_metric(MetricSpec(
    name="gross_profit_cagr_3y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CAGR Resultado Bruto 3A",
    ratio_key="gross_profit_cagr_3y",
    ratio_fn=gross_profit_cagr_3y_at,
    history_fn=gross_profit_cagr_3y_history,
    engines=["gross_profit"],
    category="growth",
    aliases=["cagr_resultado_bruto_3a", "cagr_gross_profit_3y"],
    allow_negative=True,
    tooltip="CAGR Resultado Bruto 3A = (Lucro_Bruto_atual / há_3A)^(1/3) - 1. Crescimento anualizado composto.",
))

register_metric(MetricSpec(
    name="gross_profit_cagr_5y",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="CAGR Resultado Bruto 5A",
    ratio_key="gross_profit_cagr_5y",
    ratio_fn=gross_profit_cagr_5y_at,
    history_fn=gross_profit_cagr_5y_history,
    engines=["gross_profit"],
    category="growth",
    aliases=["cagr_resultado_bruto_5a", "cagr_gross_profit_5y"],
    allow_negative=True,
    tooltip="CAGR Resultado Bruto 5A = (Lucro_Bruto_atual / há_5A)^(1/5) - 1. Crescimento anualizado composto.",
))
