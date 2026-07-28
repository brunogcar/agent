"""metrics/inventory_turnover.py -- Inventory Turnover fundamental ratio metric.

Inventory Turnover = |COGS| / Inventory
                   = |CMV| / Estoques

Measures how efficiently a company converts inventory into sales. Higher
turnover means inventory is sold and replaced quickly (efficient working-
capital management); lower turnover may indicate slow-moving stock,
overproduction, or obsolescence risk.

SIGN CONVENTION
---------------
COGS (DRE codigo 3.02) is typically reported as a NEGATIVE figure (it is
a cost/deduction from revenue). The `cogs` engine returns the RAW signed
value. We use `abs(cogs)` here so the ratio is always positive when both
inputs are present.

Inventory is a SNAPSHOT (point-in-time balance) from the `inventory`
engine (BPA codigo 1.01.04).

PERIOD MISMATCH CAVEAT
----------------------
The numerator (TTM COGS) is a 12-month flow ending at the most recent
ITR/DFP period on or before `date`. The denominator (inventory) is a
point-in-time snapshot at the most recent BPA on or before `date`. In
practice both align to the same period-end date for filers with both
BPA and DRE data, but if a filer files only annual statements, the
inventory snapshot could lag the TTM flow by up to a year. The metric
does NOT enforce date alignment -- callers should be aware of this.

Service companies and financial-sector filers typically have no inventory
line (engine returns None) -- this metric returns None for them, which
is the correct behavior.

Engines composed: cogs + inventory.

Interpretation (industry-dependent -- retail > manufacturing):
  - High turnover (e.g., 12+/year for grocery, 6+/year for apparel):
    efficient inventory management
  - Low turnover (< 3/year for non-real-estate): capital tied up in
    inventory, possible obsolescence risk

Guards:
  - inventory must be > 0 (denominator).
  - cogs must not be None. Use abs(cogs) for the ratio.
  - If either is None, return None.

Usage:
    from skills.cvm.calculations.metrics.inventory_turnover import inventory_turnover_at
    ito = inventory_turnover_at("PETR4", "2024-06-30")  # -> 5.5
"""
from __future__ import annotations

from skills.cvm.calculations.engines.cogs import cogs_at, cogs_periods
from skills.cvm.calculations.engines.inventory import inventory_at, inventory_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


def inventory_turnover_at(company: str, date: str) -> float | None:
    """Inventory Turnover = |COGS| / Inventory.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Inventory Turnover ratio as float, or None if either COGS or
        inventory is missing, or inventory <= 0.
    """
    cogs = cogs_at(company, date)
    if cogs is None:
        return None
    inventory = inventory_at(company, date)
    if inventory is None or inventory <= 0:
        return None
    return abs(cogs) / inventory


def inventory_turnover_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Inventory Turnover time series -- union of cogs + inventory dates.

    COGS dates are quarterly TTM period-end dates; inventory dates are
    quarterly BPA snapshot dates. Both typically align. Each entry
    contains the ratio plus underlying TTM COGS + inventory snapshot.
    Entries with None ratio are included so charts show gaps.
    """
    cogs_periods_list = cogs_periods(company)
    inv_periods_list = inventory_periods(company)

    all_dates = set()
    for periods in [cogs_periods_list, inv_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])
    if not all_dates:
        return []

    result = []
    for date in sorted(all_dates):
        ttm_cogs = None
        for cp in reversed(cogs_periods_list):
            if cp["date"] <= date:
                ttm_cogs = cp["ttm_cogs"]
                break
        inventory = None
        for ip in reversed(inv_periods_list):
            if ip["date"] <= date:
                inventory = ip["inventory"]
                break
        ito = None
        if (ttm_cogs is not None
                and inventory is not None and inventory > 0):
            ito = abs(ttm_cogs) / inventory
        result.append({
            "date": date,
            "inventory_turnover": ito,
            "ttm_cogs": ttm_cogs,
            "inventory": inventory,
        })
    return result


register_metric(MetricSpec(
    name="inventory_turnover",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Giro de Estoque",
    ratio_key="inventory_turnover",
    ratio_fn=inventory_turnover_at,
    history_fn=inventory_turnover_history,
    engines=["cogs", "inventory"],
    aliases=["giro_estoque", "ito", "inventory_turn"],
))
