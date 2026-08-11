"""metrics/wacc.py -- WACC (Weighted Average Cost of Capital) valuation metric.

[v2.0]

WACC = COE × (E / (D + E)) + Kd × (1 - tax) × (D / (D + E))

Where:
  COE = Cost of Equity (CAPM)        -- from coe_at() (returns FRACTION, e.g. 0.166)
  E   = Market Cap                   -- price_at() × shares_at()  (BRL)
  D   = Total Debt                   -- debt_at()                 (BRL)
  Kd  = Cost of Debt                 -- interest_paid_at() / debt_at()
                                        (falls back to financial_result_at() / debt_at()
                                         when interest_paid is None)
  tax = Effective Tax Rate           -- effective_tax_rate_at() (FRACTION, e.g. 0.25)
                                        (defaults to 0.25 -- Brazilian combined IRPJ+CSLL --
                                         when tax is None)

SIGN-HANDLING CONVENTION
-------------------------
DVA 7.08.03 (interest_paid) is reported as a NEGATIVE figure (wealth OUTFLOW).
DRE 3.06 (financial_result) is the NET figure (income - expense; negative when
expense > income). To keep Kd a POSITIVE cost-of-debt rate, we take the
absolute value of interest_paid (or financial_result) before dividing by debt.
This avoids Kd being negative (which would nonsensically REDUCE WACC).

INTERPRETATION
--------------
  - WACC < 8%:  cheap capital (low risk, low rates)
  - WACC 8-12%: typical Brazilian corporate range
  - WACC > 14%: expensive capital (high risk, high rates, or high leverage)
  - WACC = COE when debt = 0 (all-equity firm)
  - WACC = None when D+E == 0 (no capital structure) or when COE/price/shares
    are missing (can't compute the equity cost leg)

DCF USAGE
---------
WACC is the standard discount rate for DCF (Discounted Cash Flow) valuation.
Future free cash flows are discounted at WACC to compute enterprise value:
  EV = Σ FCF_t / (1 + WACC)^t

ENGINES + METRICS COMPOSED
--------------------------
  - coe (metric)            -- Cost of Equity (CAPM: Rf + β × ERP)
  - price                   -- B3 daily close (COTAHIST)
  - shares                  -- FRE shares outstanding
  - debt                    -- BPP 2.01.04 + 2.02.01 (Empréstimos e Financiamentos)
  - interest_paid (engine)  -- DVA 7.08.03 (Remuneração do Capital de Terceiros, TTM)
  - financial_result        -- DRE 3.06 (Resultado Financeiro, TTM) -- fallback Kd
  - effective_tax_rate      -- EBT-based effective tax rate

Usage:
    from skills.cvm.calculations.metrics.wacc import wacc_at, wacc_history
    w = wacc_at("PETR4", "2024-06-30")    # -> 0.12 (12% as a fraction)
    h = wacc_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations.engines.bpp.debt import debt_at, debt_periods
from skills.cvm.calculations.engines.dva.interest_paid import (
    interest_paid_at,
    interest_paid_periods,
)
from skills.cvm.calculations.engines.dre.financial_result import (
    financial_result_at,
    financial_result_periods,
)
from skills.cvm.calculations.metrics.coe import coe_at, coe_history
from skills.cvm.calculations.metrics.effective_tax_rate import (
    effective_tax_rate_at,
    effective_tax_rate_history,
)
from skills.cvm.calculations.engines.selic import selic_at
from skills.cvm.calculations._registry import MetricSpec, register_metric


# Default effective tax rate when the metric returns None.
# Brazilian combined IRPJ (15% + 10% surtax on profit > R$240k/yr) + CSLL (9%)
# ≈ 34% for large companies. The 25% default here is a conservative midpoint
# used by the rapinav2 reference implementation for missing-tax fallback.
DEFAULT_TAX_RATE = 0.25


def _compute_kd(company: str, date: str, debt: float) -> float | None:
    """Compute the pre-tax cost of debt (Kd) at a given date.

    Kd = |interest_paid| / debt   (primary, from DVA 7.08.03)
    Kd = |financial_result| / debt (fallback, from DRE 3.06 — net, less precise)

    Returns None when neither interest_paid nor financial_result is available.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.
        debt: Total debt at date (must be > 0 -- caller is responsible).

    Returns:
        Kd as a FRACTION (e.g., 0.06 for 6%), or None.
    """
    interest = interest_paid_at(company, date)
    if interest is not None:
        return abs(interest) / debt

    # Fallback: use the net financial result (less precise -- includes
    # financial income, not just interest expense on debt).
    fin_result = financial_result_at(company, date)
    if fin_result is not None:
        return abs(fin_result) / debt

    return None


# -- Ratio: WACC = COE × E/(D+E) + Kd × (1-tax) × D/(D+E) ---------------------

def wacc_at(company: str, date: str) -> float | None:
    """Compute WACC (Weighted Average Cost of Capital) at a specific date.

    WACC = COE × (E / (D + E)) + Kd × (1 - tax) × (D / (D + E))

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        WACC as a FRACTION (e.g., 0.12 for 12%), or None if:
        - COE is None (CAPM inputs missing)
        - Market Cap (E) is None (price or shares missing)
        - Debt (D) is None (BPP snapshots missing)
        - D + E == 0 (no capital structure)
        - Kd is None (interest_paid AND financial_result both missing while D > 0)
          — only when D > 0; for D == 0, WACC collapses to COE (all-equity firm).
    """
    coe = coe_at(company, date)
    if coe is None:
        # [v4 fix] COE returns None when Beta is unavailable (brapi ^BVSP
        # fails + COTAHIST proxy fails). Instead of giving up, compute a
        # rough COE = Rf + ERP (assuming Beta = 1.0, market-average risk).
        # [v1.12] Falls back to DEFAULT_RF_PCT when SGS DB is missing.
        selic_pct = selic_at(company, date)
        if selic_pct is None:
            selic_pct = 14.0  # DEFAULT_RF_PCT — current Brazilian Selic target
        rf = selic_pct / 100.0
        erp = 0.055  # Damodaran 2024 EM ERP
        coe = rf + 1.0 * erp  # Beta = 1.0 default

    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    # Market Cap (equity value)
    e = price * shares

    # Debt (book value -- market value of debt is rarely disclosed in Brazil)
    d = debt_at(company, date)
    if d is None:
        # No debt snapshot — treat as missing data, not zero debt
        return None

    # Capital structure total
    v = d + e
    if v == 0:
        return None

    # All-equity firm: WACC = COE (debt weight = 0, equity weight = 1)
    if d == 0:
        return coe

    # Cost of debt (with financial_result fallback)
    kd = _compute_kd(company, date, d)
    if kd is None:
        # [v3 fix] If neither interest_paid nor financial_result is available,
        # use a default Kd = Selic + 3% credit spread (common for Brazilian
        # corporates). [v1.12] Falls back to DEFAULT_RF_PCT when SGS missing.
        selic_pct = selic_at(company, date)
        if selic_pct is None:
            selic_pct = 14.0  # DEFAULT_RF_PCT — current Brazilian Selic target
        kd = (selic_pct + 3.0) / 100.0  # Selic (fraction) + 3% spread

    # Effective tax rate (default to Brazilian 25% if missing)
    tax = effective_tax_rate_at(company, date)
    if tax is None:
        tax = DEFAULT_TAX_RATE

    # Capital structure weights
    w_e = e / v
    w_d = d / v

    return coe * w_e + kd * (1.0 - tax) * w_d


# -- History: time series with WACC + components ------------------------------

def wacc_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute WACC time series for a date range.

    WACC changes whenever ANY component changes:
      - COE changes when Selic (daily) or Beta (rolling 30-day window) changes
      - Market Cap (E) changes when price (daily) or shares (annual) change
      - Debt (D) changes quarterly (BPP snapshots)
      - Kd changes quarterly (interest_paid / debt)
      - Effective tax rate changes quarterly (EBT / tax)

    We build the date axis from the UNION of:
      - coe_history() dates           (Selic + Beta changes)
      - price_series() dates          (daily -- dominant axis when available)
      - shares_periods() dates        (annual)
      - debt_periods() dates          (quarterly)
      - interest_paid_periods() dates (quarterly TTM)
      - effective_tax_rate_history()  (quarterly — tax + EBT changes)

    For each date, we call wacc_at() (which recomputes COE, price, shares,
    debt, Kd, tax from the *_at functions -- consistent point-in-time values).
    The dict also returns the components so consumers can show WACC bridges.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "wacc", "coe", "kd", "weights"} sorted oldest-first.
        weights = {"e": market_cap, "d": debt, "e_weight": e/(d+e), "d_weight": d/(d+e)}
        Entries with None WACC (missing inputs) are included with wacc=None
        so charts show gaps.
    """
    # Collect candidate dates from each source
    all_dates: set[str] = set()

    # coe_history (quarterly — Selic + Beta changes)
    try:
        for entry in coe_history(company, date_from, date_to):
            all_dates.add(entry["date"])
    except Exception:
        pass

    # price_series (daily — dominant axis)
    try:
        for entry in price_series(company, date_from, date_to):
            all_dates.add(entry["date"])
    except Exception:
        pass

    # shares_periods (annual step function — filter by range)
    try:
        for sp in shares_periods(company):
            if date_from <= sp["date"] <= date_to:
                all_dates.add(sp["date"])
    except Exception:
        pass

    # debt_periods (quarterly step function)
    try:
        for dp in debt_periods(company):
            if date_from <= dp["date"] <= date_to:
                all_dates.add(dp["date"])
    except Exception:
        pass

    # interest_paid_periods (quarterly TTM)
    try:
        for ip in interest_paid_periods(company):
            if date_from <= ip["date"] <= date_to:
                all_dates.add(ip["date"])
    except Exception:
        pass

    # effective_tax_rate_history (quarterly)
    try:
        for entry in effective_tax_rate_history(company, date_from, date_to):
            all_dates.add(entry["date"])
    except Exception:
        pass

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)
    result: list[dict] = []

    for date in sorted_dates:
        # Gather each component individually so we can also surface them
        # in the result dict (for WACC bridge charts).
        coe = coe_at(company, date)

        price = price_at(company, date)
        shares = shares_at(company, date)
        e = (price * shares) if (price is not None and shares is not None
                                  and price > 0 and shares > 0) else None

        d = debt_at(company, date)

        kd = None
        if d is not None and d > 0:
            kd = _compute_kd(company, date, d)

        tax = effective_tax_rate_at(company, date)
        tax_eff = tax if tax is not None else DEFAULT_TAX_RATE

        wacc: float | None = None
        weights: dict = {"e": e, "d": d, "e_weight": None, "d_weight": None}

        if (coe is not None and e is not None and d is not None
                and (d + e) != 0):
            v = d + e
            w_e = e / v
            w_d = d / v
            weights["e_weight"] = w_e
            weights["d_weight"] = w_d

            if d == 0:
                # All-equity firm: WACC = COE
                wacc = coe
            elif kd is not None:
                wacc = coe * w_e + kd * (1.0 - tax_eff) * w_d

        result.append({
            "date": date,
            "wacc": wacc,
            "coe": coe,
            "kd": kd,
            "weights": weights,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="wacc",
    per_share_label=None,        # Valuation ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="WACC",
    ratio_key="wacc",
    ratio_fn=wacc_at,
    history_fn=wacc_history,
    engines=["coe", "price", "shares", "debt", "interest_paid", "financial_result"],
    category="valuation",
    aliases=["weighted_average_cost_of_capital", "custo_medio_capital", "cmcap"],
    allow_negative=False,
    tooltip=(
        "WACC = COE × E/(D+E) + Kd×(1-tax) × D/(D+E). "
        "Custo Médio Ponderado de Capital. Discount rate for DCF."
    ),
))
