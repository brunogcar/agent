"""metrics/coe.py -- COE (Cost of Equity) via CAPM metric.

COE = Rf + Beta * (Rm - Rf)

where:
  Rf = Risk-free rate (Selic annualized, from BCB SGS)
  Beta = 5Y rolling regression vs IBOV (from beta engine)
  Rm - Rf = Market risk premium

MARKET RISK PREMIUM DESIGN DECISION:
  The equity risk premium (Rm - Rf) for Brazil is typically 5-7% based on
  academic studies (Damodaran, IPEA). We use a configurable default of 5.5%
  (the midpoint of the commonly cited range for emerging markets).

  Alternative considered: compute Rm from IBOV annual return. Rejected because:
  1. IBOV annual return is volatile (can be -20% or +30% in a single year)
  2. The CAPM premium is a forward-looking expectation, not a realized return
  3. Academic literature uses long-run averages or survey-based estimates

  The premium can be overridden by passing a custom value to coe_at().

Engines composed: selic + beta

Usage:
    from skills.cvm.calculations.metrics.coe import coe_at
    c = coe_at("PETR4", "2024-06-30")  # -> 12.5 (percent)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.selic import selic_at, selic_periods
from skills.cvm.calculations.engines.beta import beta_at, beta_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# Default equity risk premium for Brazil (Damodaran 2024: ~5.5% for emerging markets)
DEFAULT_RISK_PREMIUM = 5.5


def coe_at(company: str, date: str, risk_premium: float = None) -> float | None:
    """Compute COE (Cost of Equity) via CAPM at a specific date.

    COE = Rf + Beta * (Rm - Rf)

    Args:
        company: B3 ticker (PETR4).
        date: YYYY-MM-DD.
        risk_premium: Market risk premium Rm - Rf in percent (default: 5.5%).

    Returns:
        COE as a PERCENT (e.g., 12.5 for 12.5%), or None if:
        - Selic not available (BCB SGS not synced)
        - Beta not available (insufficient price history)
    """
    if risk_premium is None:
        risk_premium = DEFAULT_RISK_PREMIUM

    # Rf = Selic annualized (% a.a.)
    rf = selic_at(company, date)
    if rf is None:
        return None

    # Beta from 5Y regression
    beta_result = beta_at(company, date)
    if beta_result is None or beta_result.get("beta") is None:
        return None

    beta = beta_result["beta"]

    # COE = Rf + Beta * (Rm - Rf)
    coe = rf + beta * risk_premium
    return coe


def coe_history(company: str, date_from: str, date_to: str,
                risk_premium: float = None) -> list[dict]:
    """Compute COE time series for a date range.

    COE changes when Selic changes (daily) or Beta changes (monthly).
    Uses the union of Selic + Beta period dates.

    Returns:
        List of {"date", "coe", "selic", "beta"} sorted oldest-first.
    """
    if risk_premium is None:
        risk_premium = DEFAULT_RISK_PREMIUM

    selic_data = selic_periods(company)
    beta_data = beta_periods(company)

    # Build date union
    all_dates = set()
    for s in selic_data:
        if date_from <= s["date"] <= date_to:
            all_dates.add(s["date"])
    for b in beta_data:
        if date_from <= b["date"] <= date_to:
            all_dates.add(b["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)
    result = []

    for date in sorted_dates:
        # Find most recent Selic <= date
        selic = None
        for s in reversed(selic_data):
            if s["date"] <= date:
                selic = s["selic"]
                break

        # Find most recent Beta <= date
        beta_val = None
        for b in reversed(beta_data):
            if b["date"] <= date:
                beta_val = b.get("beta")
                break

        coe = None
        if selic is not None and beta_val is not None:
            coe = selic + beta_val * risk_premium

        result.append({"date": date, "coe": coe, "selic": selic, "beta": beta_val})

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="coe",
    per_share_label=None,
    per_share_key=None,
    per_share_fn=None,
    ratio_label="COE (CAPM)",
    ratio_key="coe",
    ratio_fn=coe_at,
    history_fn=coe_history,
    engines=["selic", "beta"],
    category="valuation",
    aliases=["cost_of_equity", "capm", "ke"],
))
