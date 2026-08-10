"""metrics/dupont.py -- DuPont 3-step ROE decomposition metric.

[v2.0]

DuPont Identity (3-step):
  ROE = Net Margin × Asset Turnover × Equity Multiplier

Where:
  Net Margin         = TTM Earnings / TTM Revenue       (Lucro / Receita Líquida)
  Asset Turnover     = TTM Revenue / Total Assets       (Receita / Ativo)
  Equity Multiplier  = Total Assets / Patrimônio Líquido (Ativo / PL)

The 3-step DuPont model decomposes ROE into operating efficiency (margin),
asset-use efficiency (turnover), and financial leverage (multiplier). It
explains WHY a company's ROE is what it is -- high ROE can come from any of
three sources, and each has different risk implications:

  - High margin + low turnover  → premium-pricing strategy (luxury, pharma)
  - Low margin + high turnover  → volume strategy (retail, commodities)
  - High equity multiplier      → high leverage (banks, utilities)

A 5-step DuPont further decomposes Net Margin into Tax Burden × Interest
Burden × Operating Margin -- this metric implements the simpler 3-step model.

RETURN TYPE
-----------
Unlike most metrics that return float|None, this metric is conceptually a
DECOMPOSITION (4 values). To stay compatible with the registry's
MetricSpec.ratio_fn contract (which expects float|None for summary()),
``dupont_at()`` returns the headline ROE float. The full decomposition
(4 components) is available via ``dupont_history()`` -- each entry includes
``dupont_roe`` + ``net_margin`` + ``asset_turnover`` + ``equity_multiplier``.

INTERPRETATION
--------------
  - ROE > 15%:     good (efficient equity use)
  - ROE > 20%:     excellent
  - Equity multiplier > 3:  highly leveraged (compare with industry peers)
  - Asset turnover > 1.0:   asset-light (services, tech)
  - Asset turnover < 0.5:   asset-heavy (utilities, real estate)
  - Net margin > 15%:       premium pricing

ENGINES COMPOSED
----------------
  - earnings (DRE 3.11 TTM)
  - revenue  (DRE 3.01 TTM)
  - total_assets (BPA codigo 1)
  - pl (BPP 2.03)

Usage:
    from skills.cvm.calculations.metrics.dupont import dupont_at, dupont_history
    r = dupont_at("PETR4", "2024-06-30")   # -> 0.32 (ROE = 32%)
    h = dupont_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.bpa.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations.engines.bpp.pl import pl_at, pl_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric
from skills.cvm.calculations.periods_helpers import lookup_lte


def _compute_components(
    earnings: float | None,
    revenue: float | None,
    total_assets: float | None,
    pl: float | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Compute the 4 DuPont components from raw engine values.

    Returns (net_margin, asset_turnover, equity_multiplier, roe).
    Each is None if any required input is missing/zero/negative where it
    shouldn't be.
    """
    # Net Margin = earnings / revenue
    if earnings is None or revenue is None or revenue == 0:
        net_margin = None
    else:
        net_margin = earnings / revenue

    # Asset Turnover = revenue / total_assets
    if revenue is None or total_assets is None or total_assets == 0:
        asset_turnover = None
    else:
        asset_turnover = revenue / total_assets

    # Equity Multiplier = total_assets / pl
    # PL must be > 0 (negative equity → multiplier meaningless)
    if total_assets is None or pl is None or pl <= 0:
        equity_multiplier = None
    else:
        equity_multiplier = total_assets / pl

    # ROE = net_margin × asset_turnover × equity_multiplier
    if (net_margin is not None and asset_turnover is not None
            and equity_multiplier is not None):
        roe = net_margin * asset_turnover * equity_multiplier
    else:
        roe = None

    return net_margin, asset_turnover, equity_multiplier, roe


# -- Ratio: DuPont ROE = Net Margin × Asset Turnover × Equity Multiplier -----

def dupont_at(company: str, date: str) -> float | None:
    """Compute DuPont 3-step ROE decomposition headline at a specific date.

    ROE = Net Margin × Asset Turnover × Equity Multiplier
        = (Earnings / Revenue) × (Revenue / Total Assets) × (Total Assets / PL)
        = Earnings / PL   (telescopes back to the standard ROE formula)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        ROE as a FRACTION (e.g., 0.32 for 32%), or None if:
        - revenue is 0 (Net Margin + Asset Turnover undefined)
        - total_assets is 0 (Asset Turnover + Equity Multiplier undefined)
        - PL is 0 or negative (Equity Multiplier meaningless)
        - Any input is None (missing data)
    """
    earnings = ttm_earnings_at(company, date)
    revenue = revenue_at(company, date)
    total_assets = total_assets_at(company, date)
    pl = pl_at(company, date)

    _, _, _, roe = _compute_components(earnings, revenue, total_assets, pl)
    return roe


# -- History: time series with full decomposition -----------------------------

def dupont_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute DuPont decomposition time series for a date range.

    ROE changes when any of earnings / revenue / total_assets / PL changes
    (all quarterly step functions). We build the date axis from the union
    of all 4 engines' period dates within [date_from, date_to].

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "dupont_roe", "net_margin", "asset_turnover",
                 "equity_multiplier"} sorted oldest-first.
        Entries with None ROE (missing/zero/negative inputs) are included
        with dupont_roe=None so charts show gaps.
    """
    earnings_periods = ttm_earnings_periods(company)
    revenue_periods_list = revenue_periods(company)
    total_assets_periods_list = total_assets_periods(company)
    pl_periods_list = pl_periods(company)

    # Build the union of all dates within range
    all_dates: set[str] = set()
    for periods in [
        earnings_periods, revenue_periods_list,
        total_assets_periods_list, pl_periods_list,
    ]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)
    result: list[dict] = []

    for date in sorted_dates:
        # Find most recent TTM earnings <= date
        earnings = None
        earnings = lookup_lte(earnings_periods, date, "ttm")

        # Find most recent TTM revenue <= date
        revenue = None
        revenue = lookup_lte(revenue_periods_list, date, "ttm_rev")

        # Find most recent total assets <= date
        total_assets = None
        total_assets = lookup_lte(total_assets_periods_list, date, "total_assets")

        # Find most recent PL <= date
        pl = None
        pl = lookup_lte(pl_periods_list, date, "pl")

        net_margin, asset_turnover, equity_multiplier, roe = _compute_components(
            earnings, revenue, total_assets, pl
        )

        result.append({
            "date": date,
            "dupont_roe": roe,
            "net_margin": net_margin,
            "asset_turnover": asset_turnover,
            "equity_multiplier": equity_multiplier,
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="dupont",
    per_share_label=None,        # Profitability ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="DuPont ROE",
    ratio_key="dupont_roe",
    ratio_fn=dupont_at,
    history_fn=dupont_history,
    engines=["earnings", "revenue", "total_assets", "pl"],
    category="profitability",
    aliases=["dupont_roe", "dupont_3step", "roe_dupont"],
    allow_negative=False,
    tooltip=(
        "DuPont: ROE = Margem Líquida × Giro do Ativo × Multiplicador de Capital. "
        "Decomposição da rentabilidade."
    ),
))
