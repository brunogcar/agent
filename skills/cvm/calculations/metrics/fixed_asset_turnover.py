"""metrics/fixed_asset_turnover.py -- Fixed Asset Turnover fundamental ratio metric.

Fixed Asset Turnover = Revenue / PP&E
                      = Receita Líquida / Imobilizado

Measures how efficiently a company generates sales from its long-lived
productive assets (property, plant & equipment). Higher turnover means
the company generates more revenue per BRL of fixed assets (asset-light
or highly-utilized operations); lower turnover may indicate over-
investment in capacity, idle assets, or capital-intensive operations.

NOTE: PP&E here is Imobilizado LÍQUIDO (net of accumulated depreciation),
sourced from BPA codigo 1.02.03. For gross PP&E (before accumulated
depreciation), a separate engine querying codigo 1.02.03.01 would be
needed -- flagged as a ROADMAP item. Using net PP&E is the standard
textbook convention for this ratio.

PERIOD MISMATCH CAVEAT
----------------------
The numerator (TTM revenue) is a 12-month flow ending at the most
recent ITR/DFP period on or before `date`. The denominator (PP&E) is a
point-in-time snapshot at the most recent BPA on or before `date`. In
practice both align to the same period-end date for filers with both
BPA and DRE data, but if a filer files only annual statements, the
PP&E snapshot could lag the TTM flow by up to a year. The metric does
NOT enforce date alignment -- callers should be aware of this.

Engines composed: revenue + ppe.

Interpretation (industry-dependent -- asset-light > asset-heavy):
  - High turnover (> 5.0 for manufacturing): efficient use of fixed
    assets
  - Low turnover (< 1.0): capital-intensive operations (utilities,
    telecom, heavy industry -- context-dependent, not always bad)

Guards:
  - ppe must be > 0 (denominator).
  - revenue must be > 0 (negative or zero revenue makes the ratio
    meaningless).
  - If either is None, return None.

Usage:
    from skills.cvm.calculations.metrics.fixed_asset_turnover import fixed_asset_turnover_at
    fato = fixed_asset_turnover_at("PETR4", "2024-06-30")  # -> 1.5
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.bpa.ppe import ppe_at, ppe_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


def fixed_asset_turnover_at(company: str, date: str) -> float | None:
    """Fixed Asset Turnover = Revenue / PP&E.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Fixed Asset Turnover ratio as float, or None if either revenue
        or PP&E is missing, or PP&E <= 0, or revenue <= 0.
    """
    revenue = revenue_at(company, date)
    if revenue is None or revenue <= 0:
        return None
    ppe = ppe_at(company, date)
    if ppe is None or ppe <= 0:
        return None
    return revenue / ppe


def fixed_asset_turnover_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Fixed Asset Turnover time series -- union of revenue + ppe dates.

    Revenue dates are quarterly TTM period-end dates; PP&E dates are
    quarterly BPA snapshot dates. Both typically align. Each entry
    contains the ratio plus underlying TTM revenue + PP&E snapshot.
    Entries with None ratio are included so charts show gaps.
    """
    rev_periods_list = revenue_periods(company)
    ppe_periods_list = ppe_periods(company)

    all_dates = set()
    for periods in [rev_periods_list, ppe_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_rev = None
        ttm_rev = lookup_lte(rev_periods_list, date, "ttm_rev")
        ppe = None
        ppe = lookup_lte(ppe_periods_list, date, "ppe")
        fato = None
        if (ttm_rev is not None and ttm_rev > 0
                and ppe is not None and ppe > 0):
            fato = ttm_rev / ppe
        result.append({
            "date": date,
            "fixed_asset_turnover": fato,
            "ttm_rev": ttm_rev,
            "ppe": ppe,
        })
    return result


register_metric(MetricSpec(
    name="fixed_asset_turnover",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Giro de Imobilizado",
    ratio_key="fixed_asset_turnover",
    ratio_fn=fixed_asset_turnover_at,
    history_fn=fixed_asset_turnover_history,
    engines=["revenue", "ppe"],
    category="efficiency",
    aliases=["giro_imobilizado", "fato", "fat", "fixed_asset_turn"],
))
