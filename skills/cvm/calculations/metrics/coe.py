"""metrics/coe.py -- COE (Cost of Equity) via CAPM metric.

COE = Rf + Beta * (Rm - Rf)

[v4] REVIEW FIXES:
  - P0: Uses beta_stats_at() (returns dict) instead of beta_at() (returns float).
    beta_at() is now the EngineSpec-registered function returning float|None.
  - P2: Returns FRACTION (0.166) not percent (16.6) for cross-metric consistency
    with ROE (0.35), ROIC (0.18), etc.

MARKET RISK PREMIUM DESIGN DECISION:
  The equity risk premium (Rm - Rf) for Brazil is typically 5-7% based on
  academic studies (Damodaran, IPEA). We use a configurable default of 5.5%
  (the midpoint of the commonly cited range for emerging markets).

  Default ERP is in PERCENT (5.5 = 5.5%). Internally we convert to fraction
  (0.055) for the CAPM formula, then return the result as a fraction.

Engines composed: selic + beta

Usage:
    from skills.cvm.calculations.metrics.coe import coe_at
    c = coe_at("PETR4", "2024-06-30")  # -> 0.166 (fraction, = 16.6%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.selic import selic_at, selic_periods
from skills.cvm.calculations.engines.beta import beta_stats_at, beta_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


# Default equity risk premium for Brazil (Damodaran 2024: ~5.5% for emerging markets)
# In PERCENT (5.5 = 5.5%). Converted to fraction internally.
DEFAULT_RISK_PREMIUM = 5.5

# [v1.12] Default risk-free rate when SGS DB is missing or stale.
# As of 2026, Brazil's Selic target rate is ~10.5%. Using this default
# ensures DCF/WACC/COE produce values even when sgs.db hasn't been synced
# (e.g., user only ran valuation, not bcb.macro). The default is conservative
# — it's better to have an approximate DCF than no DCF at all.
DEFAULT_RF_PCT = 10.5


def coe_at(company: str, date: str, risk_premium: float = None) -> float | None:
    """Compute COE (Cost of Equity) via CAPM at a specific date.

    COE = Rf + Beta * (Rm - Rf)

    [v4 P2] Returns FRACTION (0.166 = 16.6%) for cross-metric consistency.
    [v1.12] Falls back to DEFAULT_RF_PCT (10.5%) when SGS DB is missing,
    so DCF/WACC/COE always produce values.

    Args:
        company: B3 ticker (PETR4).
        date: YYYY-MM-DD.
        risk_premium: Market risk premium Rm - Rf in PERCENT (default: 5.5).

    Returns:
        COE as a FRACTION (e.g., 0.166 for 16.6%), or None if:
        - Beta not available (insufficient price history or R² < 0.3)
    """
    if risk_premium is None:
        risk_premium = DEFAULT_RISK_PREMIUM

    # Rf = Selic annualized (% a.a.) -> convert to fraction
    # [v1.12] Fallback to DEFAULT_RF_PCT if SGS DB missing/stale
    rf_pct = selic_at(company, date)
    if rf_pct is None:
        rf_pct = DEFAULT_RF_PCT
    rf = rf_pct / 100.0  # Convert percent to fraction

    # [v4 P0] Use beta_stats_at() for full regression stats
    beta_result = beta_stats_at(company, date)
    if beta_result is None or beta_result.get("beta") is None:
        return None

    # [new commit] Quality check: reject low-R² regressions. A beta with R²<0.3
    # means the stock's returns are poorly explained by IBOV — the regression
    # slope (beta) is statistically unreliable. Using it for CAPM would produce
    # a misleading COE. Found by external LLM review (Mistral).
    r_squared = beta_result.get("r_squared")
    if r_squared is not None and r_squared < 0.3:
        return None

    beta = beta_result["beta"]

    # ERP in fraction
    erp = risk_premium / 100.0

    # COE = Rf + Beta * (Rm - Rf), result in fraction
    coe = rf + beta * erp
    return coe


def coe_history(company: str, date_from: str, date_to: str,
                risk_premium: float = None) -> list[dict]:
    """Compute COE time series for a date range.

    [v4 P2] Returns COE as fraction (was percent).

    Returns:
        List of {"date", "coe", "selic", "beta"} sorted oldest-first.
        coe + selic are fractions; beta is the regression coefficient.
    """
    if risk_premium is None:
        risk_premium = DEFAULT_RISK_PREMIUM

    erp = risk_premium / 100.0

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
        # Find most recent Selic <= date (selic is in percent -> convert to fraction)
        selic_pct = None
        selic_pct = lookup_lte(selic_data, date, "selic")
        selic_frac = selic_pct / 100.0 if selic_pct is not None else None

        # Find most recent Beta <= date
        beta_val = None
        for b in reversed(beta_data):
            if b["date"] <= date:
                beta_val = b.get("beta")
                break

        coe = None
        if selic_frac is not None and beta_val is not None:
            coe = selic_frac + beta_val * erp

        result.append({"date": date, "coe": coe, "selic": selic_frac, "beta": beta_val})

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
    category="market",
    aliases=["cost_of_equity", "capm", "ke"],
    allow_negative=True,
    tooltip="COE = Rf + Beta × ERP. Custo de Oportunidade do Capital Próprio (CAPM). Rf=Selic, ERP=5.5% (Damodaran).",
))
