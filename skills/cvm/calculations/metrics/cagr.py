"""metrics/cagr.py -- CAGR (Compound Annual Growth Rate) metrics.

[v2.1 v2] Changed horizons from 3Y/5Y to 3M/1Y/5Y to match the Crescimento
layout. The user wants the same 3 horizons for both simple growth and CAGR.

CAGR = (V_end / V_start)^(365/lookback_days) - 1

- CAGR 3M (90 days): Annualized 3-month growth rate
- CAGR 1A (365 days): Annualized 1-year growth (= simple 1Y growth)
- CAGR 5A (1825 days): Annualized 5-year growth

Metrics registered (9 total, 3 per metric × 3 horizons):
  - revenue_cagr_3m, revenue_cagr_1y, revenue_cagr_5y
  - earnings_cagr_3m, earnings_cagr_1y, earnings_cagr_5y
  - gross_profit_cagr_3m, gross_profit_cagr_1y, gross_profit_cagr_5y

Usage:
    from skills.cvm.calculations.metrics.cagr import revenue_cagr_5y_at
    r = revenue_cagr_5y_at("PETR4", "2024-06-30")  # -> 0.1487 (= 14.87%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.dre.gross_profit import gross_profit_at, gross_profit_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def _cagr_at(periods: list[dict], target_date: str, lookback_days: int,
             value_key: str = "value") -> float | None:
    """Compute CAGR at target_date over a lookback window.

    CAGR = (V_end / V_start)^(365/lookback_days) - 1

    [v2.1] Uses explicit value_key parameter instead of OR chain.

    Args:
        periods: List of {"date": str, value_key: float} sorted oldest-first.
        target_date: YYYY-MM-DD.
        lookback_days: 90 for 3M, 365 for 1Y, 1825 for 5Y.
        value_key: The dict key that holds the numeric value in each period.
    """
    from datetime import date as _date, timedelta as _timedelta

    try:
        target = _date.fromisoformat(target_date)
    except (ValueError, TypeError):
        return None

    v_end = None
    end_date = None
    for p in reversed(periods):
        try:
            p_date = _date.fromisoformat(p["date"])
        except (ValueError, KeyError, TypeError):
            continue
        if p_date <= target:
            val = p.get(value_key)
            if val is not None and val > 0:
                v_end = float(val)
                end_date = p_date
                break

    if v_end is None or v_end <= 0:
        return None

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
        val = p.get(value_key)
        if val is not None and val > 0:
            diff = abs((p_date - target_start).days)
            if best_diff is None or diff < best_diff:
                if diff <= lookback_days * 1.5:
                    best_diff = diff
                    v_start = float(val)
                    start_date = p_date

    if v_start is None or v_start <= 0:
        return None

    if end_date is None or start_date is None:
        return None
    actual_days = (end_date - start_date).days
    if actual_days <= 0:
        return None

    years = actual_days / 365.0
    if years < 0.1:  # [v2.1 v3] Was 0.5 — blocked 3M CAGR (0.25 years). Now 0.1 (36 days min).
        return None

    ratio = v_end / v_start
    if ratio <= 0:
        return None

    cagr = ratio ** (1.0 / years) - 1.0
    return cagr


# ── Revenue CAGR ──────────────────────────────────────────────────────────────

def revenue_cagr_3m_at(company: str, date: str) -> float | None:
    """Revenue CAGR over 3 months (annualized)."""
    periods = revenue_periods(company)
    return _cagr_at(periods, date, 90, value_key="ttm_rev")

def revenue_cagr_1y_at(company: str, date: str) -> float | None:
    """Revenue CAGR over 1 year."""
    periods = revenue_periods(company)
    return _cagr_at(periods, date, 365, value_key="ttm_rev")

def revenue_cagr_5y_at(company: str, date: str) -> float | None:
    """Revenue CAGR over 5 years."""
    periods = revenue_periods(company)
    return _cagr_at(periods, date, 1825, value_key="ttm_rev")


# ── Earnings CAGR ─────────────────────────────────────────────────────────────

def earnings_cagr_3m_at(company: str, date: str) -> float | None:
    """Earnings CAGR over 3 months (annualized)."""
    periods = ttm_earnings_periods(company)
    return _cagr_at(periods, date, 90, value_key="ttm")

def earnings_cagr_1y_at(company: str, date: str) -> float | None:
    """Earnings CAGR over 1 year."""
    periods = ttm_earnings_periods(company)
    return _cagr_at(periods, date, 365, value_key="ttm")

def earnings_cagr_5y_at(company: str, date: str) -> float | None:
    """Earnings CAGR over 5 years."""
    periods = ttm_earnings_periods(company)
    return _cagr_at(periods, date, 1825, value_key="ttm")


# ── Gross Profit CAGR ─────────────────────────────────────────────────────────

def gross_profit_cagr_3m_at(company: str, date: str) -> float | None:
    """Gross profit CAGR over 3 months (annualized)."""
    periods = gross_profit_periods(company)
    return _cagr_at(periods, date, 90, value_key="ttm_gp")

def gross_profit_cagr_1y_at(company: str, date: str) -> float | None:
    """Gross profit CAGR over 1 year."""
    periods = gross_profit_periods(company)
    return _cagr_at(periods, date, 365, value_key="ttm_gp")

def gross_profit_cagr_5y_at(company: str, date: str) -> float | None:
    """Gross profit CAGR over 5 years."""
    periods = gross_profit_periods(company)
    return _cagr_at(periods, date, 1825, value_key="ttm_gp")


# ── History functions (stub — CAGR history not commonly used) ─────────────────

def _cagr_history(periods, date_from, date_to, lookback, value_key, result_key):
    """Generic CAGR history time series."""
    result = []
    from datetime import date as _date, timedelta as _timedelta
    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        return []
    current = d_from
    while current <= d_to:
        val = _cagr_at(periods, current.isoformat(), lookback, value_key=value_key)
        result.append({"date": current.isoformat(), result_key: val})
        current += _timedelta(days=90)
    return result


def revenue_cagr_3m_history(c, df, dt): return _cagr_history(revenue_periods(c), df, dt, 90, "ttm_rev", "revenue_cagr_3m")
def revenue_cagr_1y_history(c, df, dt): return _cagr_history(revenue_periods(c), df, dt, 365, "ttm_rev", "revenue_cagr_1y")
def revenue_cagr_5y_history(c, df, dt): return _cagr_history(revenue_periods(c), df, dt, 1825, "ttm_rev", "revenue_cagr_5y")
def earnings_cagr_3m_history(c, df, dt): return _cagr_history(ttm_earnings_periods(c), df, dt, 90, "ttm", "earnings_cagr_3m")
def earnings_cagr_1y_history(c, df, dt): return _cagr_history(ttm_earnings_periods(c), df, dt, 365, "ttm", "earnings_cagr_1y")
def earnings_cagr_5y_history(c, df, dt): return _cagr_history(ttm_earnings_periods(c), df, dt, 1825, "ttm", "earnings_cagr_5y")
def gross_profit_cagr_3m_history(c, df, dt): return _cagr_history(gross_profit_periods(c), df, dt, 90, "ttm_gp", "gross_profit_cagr_3m")
def gross_profit_cagr_1y_history(c, df, dt): return _cagr_history(gross_profit_periods(c), df, dt, 365, "ttm_gp", "gross_profit_cagr_1y")
def gross_profit_cagr_5y_history(c, df, dt): return _cagr_history(gross_profit_periods(c), df, dt, 1825, "ttm_gp", "gross_profit_cagr_5y")


# ── Register 9 CAGR metrics (3M/1A/5A × 3 metrics) ───────────────────────────

_CAGR_REGS = [
    # Revenue
    ("revenue_cagr_3m", "CAGR Receita 3M", revenue_cagr_3m_at, revenue_cagr_3m_history, ["revenue"], ["cagr_receita_3m"],
     "CAGR Receita 3M = (Receita_atual / Receita_3M_atrás)^(365/90) - 1. Crescimento anualizado de 3 meses."),
    ("revenue_cagr_1y", "CAGR Receita 1A", revenue_cagr_1y_at, revenue_cagr_1y_history, ["revenue"], ["cagr_receita_1a"],
     "CAGR Receita 1A = (Receita_atual / Receita_1A_atrás) - 1. Crescimento anualizado de 1 ano."),
    ("revenue_cagr_5y", "CAGR Receita 5A", revenue_cagr_5y_at, revenue_cagr_5y_history, ["revenue"], ["cagr_receita_5a"],
     "CAGR Receita 5A = (Receita_atual / Receita_5A_atrás)^(1/5) - 1. Crescimento anualizado de 5 anos."),
    # Earnings
    ("earnings_cagr_3m", "CAGR Lucro 3M", earnings_cagr_3m_at, earnings_cagr_3m_history, ["earnings"], ["cagr_lucro_3m"],
     "CAGR Lucro 3M = (Lucro_atual / Lucro_3M_atrás)^(365/90) - 1. Crescimento anualizado de 3 meses."),
    ("earnings_cagr_1y", "CAGR Lucro 1A", earnings_cagr_1y_at, earnings_cagr_1y_history, ["earnings"], ["cagr_lucro_1a"],
     "CAGR Lucro 1A = (Lucro_atual / Lucro_1A_atrás) - 1. Crescimento anualizado de 1 ano."),
    ("earnings_cagr_5y", "CAGR Lucro 5A", earnings_cagr_5y_at, earnings_cagr_5y_history, ["earnings"], ["cagr_lucro_5a"],
     "CAGR Lucro 5A = (Lucro_atual / Lucro_5A_atrás)^(1/5) - 1. Crescimento anualizado de 5 anos."),
    # Gross Profit
    ("gross_profit_cagr_3m", "CAGR Resultado Bruto 3M", gross_profit_cagr_3m_at, gross_profit_cagr_3m_history, ["gross_profit"], ["cagr_resultado_bruto_3m"],
     "CAGR Resultado Bruto 3M = (Lucro_Bruto_atual / há_3M)^(365/90) - 1. Crescimento anualizado de 3 meses."),
    ("gross_profit_cagr_1y", "CAGR Resultado Bruto 1A", gross_profit_cagr_1y_at, gross_profit_cagr_1y_history, ["gross_profit"], ["cagr_resultado_bruto_1a"],
     "CAGR Resultado Bruto 1A = (Lucro_Bruto_atual / há_1A) - 1. Crescimento anualizado de 1 ano."),
    ("gross_profit_cagr_5y", "CAGR Resultado Bruto 5A", gross_profit_cagr_5y_at, gross_profit_cagr_5y_history, ["gross_profit"], ["cagr_resultado_bruto_5a"],
     "CAGR Resultado Bruto 5A = (Lucro_Bruto_atual / há_5A)^(1/5) - 1. Crescimento anualizado de 5 anos."),
]

for name, label, fn, hist_fn, engines, aliases, tooltip in _CAGR_REGS:
    register_metric(MetricSpec(
        name=name,
        per_share_label=None, per_share_key=None, per_share_fn=None,
        ratio_label=label,
        ratio_key=name,
        ratio_fn=fn,
        history_fn=hist_fn,
        engines=engines,
        category="growth",
        aliases=aliases,
        allow_negative=True,
        tooltip=tooltip,
    ))
