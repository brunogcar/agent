"""metrics/roic.py -- ROIC (Return on Invested Capital) fundamental ratio metric.

ROIC = NOPAT / Invested Capital

Where:
  NOPAT (Net Operating Profit After Tax) = EBIT - max(0, tax)
    - EBIT = TTM EBIT (DRE 3.05)
    - tax = TTM IR+CSLL (DRE 3.08, typically negative -- we use max(0, -tax)
      to get the positive tax expense)
  Invested Capital = PL + Debt
    - PL = Patrimônio Líquido (BPP 2.03)
    - Debt = Empréstimos e Financiamentos (BPP 2.01.04 + 2.02.01)

NOTE: This is a SIMPLIFIED ROIC. The exact formula subtracts cash from
invested capital (IC = PL + Debt - Cash), but we don't have a cash engine
yet (planned for EV/EBITDA in Tier 3). Without cash subtraction, ROIC is
conservatively underestimated (higher denominator). When the cash engine
is added, this metric can be updated.

Also, NOPAT = EBIT - tax is an approximation. The exact formula is
NOPAT = EBIT × (1 - tax_rate) where tax_rate = tax / pre_tax_income.
We don't have a pre_tax_income engine. The approximation is acceptable
for most use cases -- it slightly overestimates NOPAT when financial
expenses are high (tax is on pre-tax income, not EBIT).

ROIC is a FUNDAMENTAL RATIO -- no price, no shares engines.

Engines composed: ebit + tax + pl + debt

Interpretation:
  - ROIC > 15%: excellent (creating value above cost of capital)
  - ROIC > WACC: company is creating value
  - ROIC < WACC: company is destroying value
  - ROIC < 0%: operating losses after tax
  - Compare ROIC to ROE: if ROE >> ROIC, the company uses leverage

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.metrics.roic import roic_at, roic_history
    r = roic_at("PETR4", "2024-06-30")    # -> 0.18 (18%)
"""
from __future__ import annotations

from skills.cvm.historical.engines.ebit import ebit_at, ebit_periods
from skills.cvm.historical.engines.tax import tax_at, tax_periods
from skills.cvm.historical.engines.pl import pl_at, pl_periods
from skills.cvm.historical.engines.debt import debt_at, debt_periods
from skills.cvm.historical._registry import MetricSpec, register_metric


# -- Ratio: ROIC = NOPAT / Invested Capital ---------------------------------

def roic_at(company: str, date: str) -> float | None:
    """Compute ROIC (Return on Invested Capital) at a specific date.

    ROIC = NOPAT / Invested Capital
    NOPAT = EBIT - tax_expense (where tax_expense = max(0, -tax))
    Invested Capital = PL + Debt

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        ROIC as a fraction (0.18 = 18%), or None if:
        - EBIT is None or <= 0 (operating losses -- ROIC meaningless)
        - PL is None or <= 0 (negative equity)
        - Debt is None (no debt data)
        - Invested Capital <= 0
    """
    ebit = ebit_at(company, date)
    if ebit is None or ebit <= 0:
        return None  # Operating losses -- ROIC meaningless

    # Tax is typically negative on DRE (expense). We want the positive
    # tax expense: max(0, -tax). If tax is None or positive (tax credit),
    # tax_expense = 0.
    tax = tax_at(company, date)
    if tax is not None and tax < 0:
        tax_expense = -tax  # Convert negative DRE value to positive expense
    else:
        tax_expense = 0.0

    # NOPAT = EBIT - tax_expense
    nopat = ebit - tax_expense
    if nopat <= 0:
        return None  # NOPAT <= 0 -- ROIC meaningless

    # Invested Capital = PL + Debt
    pl = pl_at(company, date)
    if pl is None or pl <= 0:
        return None

    debt = debt_at(company, date)
    if debt is None:
        return None  # No debt data -- can't compute IC

    invested_capital = pl + debt
    if invested_capital <= 0:
        return None

    return nopat / invested_capital


# -- History: series with ROIC (no price, no shares) -------------------------

def roic_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute ROIC time series for a date range.

    ROIC changes when EBIT (quarterly), tax (quarterly), PL (quarterly),
    or debt (quarterly) change. No daily price driver -- series based on
    union of all 4 engine period dates.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "roic", "ttm_ebit", "ttm_tax", "pl", "debt"}
        sorted oldest-first. Entries with None ROE (negative earnings/equity,
        missing data) are included with roe=None so charts show gaps.
    """
    ebit_periods_list = ebit_periods(company)
    tax_periods_list = tax_periods(company)
    pl_periods_list = pl_periods(company)
    debt_periods_list = debt_periods(company)

    # Build a union of all dates from all 4 engines
    all_dates = set()
    for periods in [ebit_periods_list, tax_periods_list, pl_periods_list, debt_periods_list]:
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

        # Compute NOPAT = EBIT - tax_expense
        nopat = None
        if ttm_ebit is not None and ttm_ebit > 0:
            tax_expense = 0.0
            if ttm_tax is not None and ttm_tax < 0:
                tax_expense = -ttm_tax
            nopat = ttm_ebit - tax_expense

        # Compute ROIC = NOPAT / Invested Capital
        roic = None
        if (nopat is not None and nopat > 0
            and pl is not None and pl > 0
            and debt is not None
            and (pl + debt) > 0):
            roic = nopat / (pl + debt)

        result.append({
            "date": date,
            "roic": roic,
            "ttm_ebit": ttm_ebit,
            "ttm_tax": ttm_tax,
            "pl": pl,
            "debt": debt,
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
    engines=["ebit", "tax", "pl", "debt"],
    aliases=["return_on_invested_capital", "retorno_capital_investido"],
))
