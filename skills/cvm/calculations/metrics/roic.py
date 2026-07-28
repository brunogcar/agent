"""metrics/roic.py -- ROIC (Return on Invested Capital) fundamental ratio metric.

ROIC = NOPAT / Invested Capital

Where:
  NOPAT (Net Operating Profit After Tax) = EBIT × (1 - effective_tax_rate)
    - EBIT = TTM EBIT (DRE 3.05)
    - effective_tax_rate = tax_expense / EBT (DRE 3.08 / DRE 3.07)
    - tax_expense = abs(tax) when tax < 0 (DRE stores tax as negative expense)
    - Clamped to [0, 0.50] (max 50% for Brazil's combined IRPJ+CSLL rate)
  Invested Capital = PL + Debt - Cash
    - PL = Patrimônio Líquido (BPP 2.03)
    - Debt = Empréstimos e Financiamentos (BPP 2.01.04 + 2.02.01)
    - Cash = Caixa e Equivalentes (BPA 1.01.01) — subtracted (excess cash is not invested capital)

ROIC is a FUNDAMENTAL RATIO -- no price, no shares engines.

Engines composed: ebit + tax + ebt + pl + debt + cash

Interpretation:
  - ROIC > 15%: excellent (creating value above cost of capital)
  - ROIC > WACC: company is creating value
  - ROIC < WACC: company is destroying value
  - ROIC < 0%: operating losses after tax
  - Compare ROIC to ROE: if ROE >> ROIC, the company uses leverage

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.roic import roic_at, roic_history
    r = roic_at("PETR4", "2024-06-30")    # -> 0.18 (18%)
"""
from __future__ import annotations

from skills.cvm.calculations.engines.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.tax import tax_at, tax_periods
from skills.cvm.calculations.engines.ebt import ebt_at, ebt_periods
from skills.cvm.calculations.engines.pl import pl_at, pl_periods
from skills.cvm.calculations.engines.debt import debt_at, debt_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# Maximum effective tax rate we apply when computing NOPAT. Brazil's combined
# IRPJ (15% + 10% surtax on profit > R$240k/yr) + CSLL (9%) = 34%, but we
# allow up to 50% to absorb deferred-tax adjustments and special situations
# without producing a negative NOPAT on profitable companies.
_MAX_EFFECTIVE_TAX_RATE = 0.50


# -- Ratio: ROIC = NOPAT / Invested Capital ---------------------------------

def roic_at(company: str, date: str) -> float | None:
    """Compute ROIC (Return on Invested Capital) at a specific date.

    ROIC = NOPAT / Invested Capital
    NOPAT = EBIT × (1 - effective_tax_rate)
      where effective_tax_rate = tax_expense / EBT, clamped to [0, 0.50]
    Invested Capital = PL + Debt - Cash

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        ROIC as a fraction (0.18 = 18%), or None if:
        - EBIT is None or <= 0 (operating losses -- ROIC meaningless)
        - EBT is None or <= 0 (can't compute tax rate without pre-tax income)
        - PL is None or <= 0 (negative equity)
        - Debt is None (no debt data)
        - Invested Capital <= 0
    """
    ebit = ebit_at(company, date)
    if ebit is None or ebit <= 0:
        return None  # Operating losses -- ROIC meaningless

    # EBT (pre-tax income) is required to compute the effective tax rate.
    # Without pre-tax income, we can't compute a meaningful tax rate, and
    # using a flat tax rate (e.g. 34%) would produce misleading NOPAT.
    ebt = ebt_at(company, date)
    if ebt is None or ebt <= 0:
        return None  # Can't compute effective tax rate without positive EBT

    # Tax is typically negative on DRE (expense). We want the positive
    # tax expense: max(0, -tax). If tax is None or positive (tax credit),
    # tax_expense = 0.
    tax = tax_at(company, date)
    if tax is not None and tax < 0:
        tax_expense = -tax  # Convert negative DRE value to positive expense
    else:
        tax_expense = 0.0

    # Effective tax rate = tax_expense / EBT. Clamp to [0, 0.50]:
    # - Floor 0: tax credits / zero-tax situations don't inflate NOPAT
    # - Ceiling 50%: Brazil's combined IRPJ+CSLL is 34% (15+10+9); 50%
    #   absorbs deferred-tax adjustments without producing negative NOPAT
    effective_tax_rate = tax_expense / ebt if ebt > 0 else 0.0
    effective_tax_rate = min(max(effective_tax_rate, 0.0), _MAX_EFFECTIVE_TAX_RATE)

    # NOPAT = EBIT × (1 - effective_tax_rate) -- correct formula.
    # (v1.x used NOPAT = EBIT - tax_expense, which slightly overestimates
    # NOPAT when financial expenses are high because tax is on pre-tax
    # income, not on EBIT. v2.0 uses the proper EBT-based effective rate.)
    nopat = ebit * (1.0 - effective_tax_rate)
    if nopat <= 0:
        return None  # NOPAT <= 0 -- ROIC meaningless

    # Invested Capital = PL + Debt - Cash (v1.9: cash subtraction)
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None

    debt = debt_at(company, date)
    if debt is None:
        return None  # No debt data -- can't compute IC

    # Cash subtraction (v1.9): if cash data available, subtract from IC.
    # This makes ROIC more accurate -- excess cash is not "invested capital".
    # If cash is None (no data), fall back to PL + Debt (v1.8 behavior).
    # Wrapped in try/except so tests without a cash engine mock don't break.
    try:
        from skills.cvm.calculations.engines.cash import cash_at as _cash_at
        cash = _cash_at(company, date)
    except Exception:
        cash = None
    if cash is not None and cash > 0:
        invested_capital = pl + debt - cash
    else:
        invested_capital = pl + debt

    if invested_capital <= 0:
        return None

    return nopat / invested_capital


# -- History: series with ROIC (no price, no shares) -------------------------

def roic_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute ROIC time series for a date range.

    ROIC changes when EBIT (quarterly), tax (quarterly), EBT (quarterly),
    PL (quarterly), debt (quarterly), or cash (quarterly) change. No daily
    price driver -- series based on union of all 6 engine period dates.

    v1.9: now subtracts cash from invested capital (IC = PL + Debt - Cash).
    v2.0: now uses EBT to compute effective tax rate (NOPAT = EBIT × (1 - rate)).

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "roic", "ttm_ebit", "ttm_tax", "ttm_ebt", "pl",
                 "debt", "cash"} sorted oldest-first. Entries with None ROIC
        are included with roic=None so charts show gaps.
    """
    from skills.cvm.calculations.engines.cash import cash_periods as _cash_periods

    ebit_periods_list = ebit_periods(company)
    tax_periods_list = tax_periods(company)
    ebt_periods_list = ebt_periods(company)
    pl_periods_list = pl_periods(company)
    debt_periods_list = debt_periods(company)
    try:
        cash_periods_list = _cash_periods(company)
    except Exception:
        cash_periods_list = []

    # Build a union of all dates from all 6 engines
    all_dates = set()
    for periods in [ebit_periods_list, tax_periods_list, ebt_periods_list,
                    pl_periods_list, debt_periods_list, cash_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)

    result = []
    for date in sorted_dates:
        # Find most recent EBIT <= date
        ttm_ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ttm_ebit = ep["ttm_ebit"]
                break

        # Find most recent tax <= date
        ttm_tax = None
        for tp in reversed(tax_periods_list):
            if tp["date"] <= date:
                ttm_tax = tp["ttm_tax"]
                break

        # Find most recent EBT <= date (v2.0)
        ttm_ebt = None
        for ep in reversed(ebt_periods_list):
            if ep["date"] <= date:
                ttm_ebt = ep["ttm_ebt"]
                break

        # Find most recent PL <= date
        pl = None
        for pp in reversed(pl_periods_list):
            if pp["date"] <= date:
                pl = pp["pl"]
                break

        # Find most recent debt <= date
        debt = None
        for dp in reversed(debt_periods_list):
            if dp["date"] <= date:
                debt = dp["debt"]
                break

        # Find most recent cash <= date (v1.9)
        cash = None
        for cp in reversed(cash_periods_list):
            if cp["date"] <= date:
                cash = cp["cash"]
                break

        # Compute NOPAT = EBIT × (1 - effective_tax_rate)  (v2.0)
        # effective_tax_rate = tax_expense / EBT, clamped to [0, 0.50]
        # Requires EBIT > 0 AND EBT > 0.
        nopat = None
        if ttm_ebit is not None and ttm_ebit > 0 and ttm_ebt is not None and ttm_ebt > 0:
            tax_expense = 0.0
            if ttm_tax is not None and ttm_tax < 0:
                tax_expense = -ttm_tax
            effective_tax_rate = min(max(tax_expense / ttm_ebt, 0.0),
                                     _MAX_EFFECTIVE_TAX_RATE)
            nopat = ttm_ebit * (1.0 - effective_tax_rate)

        # Compute Invested Capital = PL + Debt - Cash (v1.9)
        # If cash is None, fall back to PL + Debt (v1.8 behavior)
        invested_capital = None
        if pl is not None and pl > 0 and debt is not None:
            if cash is not None and cash > 0:
                invested_capital = pl + debt - cash
            else:
                invested_capital = pl + debt

        # Compute ROIC = NOPAT / Invested Capital
        roic = None
        if (nopat is not None and nopat > 0
            and invested_capital is not None and invested_capital > 0):
            roic = nopat / invested_capital

        result.append({
            "date": date,
            "roic": roic,
            "ttm_ebit": ttm_ebit,
            "ttm_tax": ttm_tax,
            "ttm_ebt": ttm_ebt,
            "pl": pl,
            "debt": debt,
            "cash": cash,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="roic",
    per_share_label=None,
    per_share_key=None,
    per_share_fn=None,
    ratio_label="ROIC",
    ratio_key="roic",
    ratio_fn=roic_at,
    history_fn=roic_history,
    engines=["ebit", "tax", "ebt", "pl", "debt", "cash"],
    aliases=["return_on_invested_capital", "retorno_capital_investido"],
))
