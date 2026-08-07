"""metrics/altman_z.py -- Altman Z-Score (bankruptcy prediction) metric.

[v2.0]

Altman Z-Score (original 1968 manufacturing model):
  Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5

Where:
  X1 = Working Capital / Total Assets
     = (current_assets - current_liabilities) / total_assets
  X2 = Retained Earnings / Total Assets
     [PROXY used here: PL / total_assets -- see note below]
  X3 = EBIT / Total Assets            (TTM EBIT from DRE 3.05)
  X4 = Market Cap / Total Liabilities
     = (price × shares) / (total_assets - PL)
     [Total Liabilities = Ativo - PL, since Ativo = Passivo + PL]
  X5 = Sales / Total Assets            (TTM Revenue from DRE 3.01)

PROXY NOTE FOR X2
-----------------
The proper numerator for X2 is RETAINED EARNINGS (Lucros Acumulados),
which is CVM BPP codes 2.03.03 + 2.03.04 (Lucros Acumulados + Reservas de
Lucros). We don't currently have a dedicated engine for that line, so we
use total Patrimônio Líquido (BPP 2.03) as a PROXY. This is a
SIMPLIFICATION — it overstates X2 for companies with significant share
capital or capital reserves, and understates it for companies with large
accumulated losses. The proper fix is a future engine that sums BPP
2.03.03 + 2.03.04 + 2.03.05 (Reservas de Capital). When that engine
exists, swap the import + replace ``pl_at`` with ``retained_earnings_at``.

INTERPRETATION
--------------
  - Z > 2.99:    "safe" zone     (low bankruptcy risk)
  - 1.81 < Z < 2.99: "grey" zone (moderate risk — monitor closely)
  - Z < 1.81:    "distress" zone (high risk — restructure or default likely)
  - Z < 0:       severe distress (negative working capital, negative equity,
                 or operating losses — immediate red flag)

The Z-Score was calibrated on US manufacturing companies (1968). For
Brazilian companies, the thresholds are approximate — local academic studies
suggest slightly lower cutoffs (e.g., 2.5 / 1.5) due to higher interest
rates and different capital structures. We retain the original cutoffs for
cross-study comparability.

CAVEAT
------
The original Altman model targets MANUFACTURING firms. Service / financial /
utility firms have different capital structures, and the model's
discriminatory power is lower for them. There are revised models (Z'-Score
for private firms, Z''-Score for non-manufacturers) — this metric implements
the ORIGINAL manufacturing model only.

ENGINES COMPOSED
----------------
  - current_assets (BPA 1.01)
  - current_liabilities (BPP 2.01)
  - total_assets (BPA 1)
  - pl (BPP 2.03)              [PROXY for retained earnings — see note]
  - ebit (DRE 3.05 TTM)
  - revenue (DRE 3.01 TTM)
  - price (COTAHIST)
  - shares (FRE)

Usage:
    from skills.cvm.calculations.metrics.altman_z import altman_z_at, altman_z_history
    z = altman_z_at("PETR4", "2024-06-30")   # -> 3.5 (safe zone)
    h = altman_z_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.bpa.current_assets import current_assets_at
from skills.cvm.calculations.engines.bpp.current_liabilities import current_liabilities_at
from skills.cvm.calculations.engines.bpa.total_assets import total_assets_at, total_assets_periods
from skills.cvm.calculations.engines.bpp.pl import pl_at
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.engines.shares import shares_at
from skills.cvm.calculations._registry import MetricSpec, register_metric


# Altman's coefficients (original 1968 manufacturing model)
COEF_X1 = 1.2  # Working Capital / Total Assets
COEF_X2 = 1.4  # Retained Earnings / Total Assets (PROXY: PL / Total Assets)
COEF_X3 = 3.3  # EBIT / Total Assets
COEF_X4 = 0.6  # Market Cap / Total Liabilities
COEF_X5 = 1.0  # Sales / Total Assets

# Zone thresholds
SAFE_THRESHOLD = 2.99       # Z > 2.99 → safe
DISTRESS_THRESHOLD = 1.81   # Z < 1.81 → distress


def _zone(z: float | None) -> str | None:
    """Classify a Z-score into a bankruptcy risk zone.

    Returns "safe" / "grey" / "distress", or None when z is None.
    """
    if z is None:
        return None
    if z > SAFE_THRESHOLD:
        return "safe"
    if z < DISTRESS_THRESHOLD:
        return "distress"
    return "grey"


# -- Ratio: Altman Z-Score ----------------------------------------------------

def altman_z_at(company: str, date: str) -> float | None:
    """Compute Altman Z-Score (original manufacturing model) at a specific date.

    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Altman Z-Score as a float (can be negative for highly distressed
        companies), or None if:
        - total_assets is None or 0 (X1, X2, X3, X5 undefined)
        - Total Liabilities (total_assets - PL) is 0 (X4 division by zero)
        - Any other input is None (current_assets, current_liabilities, pl,
          ebit, revenue, price, shares)
    """
    total_assets = total_assets_at(company, date)
    if total_assets is None or total_assets == 0:
        return None

    pl = pl_at(company, date)
    if pl is None:
        return None

    # Total Liabilities = Ativo - PL (since Ativo = Passivo + PL)
    total_liabilities = total_assets - pl
    if total_liabilities == 0:
        return None  # X4 division by zero

    current_assets = current_assets_at(company, date)
    if current_assets is None:
        return None

    current_liabilities = current_liabilities_at(company, date)
    if current_liabilities is None:
        return None

    ebit = ebit_at(company, date)
    if ebit is None:
        return None

    revenue = revenue_at(company, date)
    if revenue is None:
        return None

    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    market_cap = price * shares

    # X1 = Working Capital / Total Assets
    x1 = (current_assets - current_liabilities) / total_assets
    # X2 = Retained Earnings / Total Assets  [PROXY: PL / Total Assets]
    x2 = pl / total_assets
    # X3 = EBIT / Total Assets
    x3 = ebit / total_assets
    # X4 = Market Cap / Total Liabilities
    # NOTE: If PL > Total Assets (negative liabilities), X4 will be negative —
    # we still compute it (the task allows this edge case).
    x4 = market_cap / total_liabilities
    # X5 = Sales / Total Assets
    x5 = revenue / total_assets

    return (COEF_X1 * x1 + COEF_X2 * x2 + COEF_X3 * x3
            + COEF_X4 * x4 + COEF_X5 * x5)


# -- History: time series with all 5 X-components + Z + zone ------------------

def altman_z_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute Altman Z-Score time series for a date range.

    The Z-Score's TTM drivers (EBIT + Revenue) change quarterly when new
    ITR/DFP filings arrive. The snapshot drivers (total_assets, PL, current_*
    ) also change quarterly. Market Cap (price × shares) changes daily, but
    for a bankruptcy-prediction metric, daily noise isn't useful — we want
    the structural trend. We build the date axis from the union of the
    quarterly TTM engines (total_assets + revenue + ebit), which captures
    every structural change.

    For each date, we call altman_z_at() to compute Z, plus we compute the
    5 X-components individually for the decomposition chart.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "altman_z", "x1", "x2", "x3", "x4", "x5", "zone"}
        sorted oldest-first.
        Entries with None Z (missing inputs) are included with altman_z=None
        and zone=None so charts show gaps.
    """
    total_assets_periods_list = total_assets_periods(company)
    revenue_periods_list = revenue_periods(company)
    ebit_periods_list = ebit_periods(company)

    # Build the union of dates within range
    all_dates: set[str] = set()
    for periods in [total_assets_periods_list, revenue_periods_list, ebit_periods_list]:
        for p in periods:
            if date_from <= p["date"] <= date_to:
                all_dates.add(p["date"])

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)
    result: list[dict] = []

    for date in sorted_dates:
        # Find most recent total_assets <= date
        total_assets = None
        for tp in reversed(total_assets_periods_list):
            if tp["date"] <= date:
                total_assets = tp["total_assets"]
                break

        # Find most recent TTM revenue <= date
        revenue = None
        for rp in reversed(revenue_periods_list):
            if rp["date"] <= date:
                revenue = rp["ttm_rev"]
                break

        # Find most recent TTM EBIT <= date
        ebit = None
        for ep in reversed(ebit_periods_list):
            if ep["date"] <= date:
                ebit = ep["ttm_ebit"]
                break

        # Snapshot engines — call *_at for point-in-time values
        pl = pl_at(company, date)
        current_assets = current_assets_at(company, date)
        current_liabilities = current_liabilities_at(company, date)
        price = price_at(company, date)
        shares = shares_at(company, date)

        z: float | None = None
        x1 = x2 = x3 = x4 = x5 = None

        if (total_assets is not None and total_assets != 0
                and pl is not None
                and current_assets is not None
                and current_liabilities is not None
                and ebit is not None
                and revenue is not None
                and price is not None and price > 0
                and shares is not None and shares > 0):

            total_liabilities = total_assets - pl
            if total_liabilities != 0:
                market_cap = price * shares
                x1 = (current_assets - current_liabilities) / total_assets
                x2 = pl / total_assets
                x3 = ebit / total_assets
                x4 = market_cap / total_liabilities
                x5 = revenue / total_assets
                z = (COEF_X1 * x1 + COEF_X2 * x2 + COEF_X3 * x3
                     + COEF_X4 * x4 + COEF_X5 * x5)

        result.append({
            "date": date,
            "altman_z": z,
            "x1": x1,
            "x2": x2,
            "x3": x3,
            "x4": x4,
            "x5": x5,
            "zone": _zone(z),
        })

    return result


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="altman_z",
    per_share_label=None,        # Leverage ratio -- no per-share value
    per_share_key=None,
    per_share_fn=None,
    ratio_label="Altman Z-Score",
    ratio_key="altman_z",
    ratio_fn=altman_z_at,
    history_fn=altman_z_history,
    engines=[
        "current_assets", "current_liabilities", "total_assets", "pl",
        "ebit", "revenue", "price", "shares",
    ],
    category="leverage",
    aliases=["altman_zscore", "zscore", "altman", "risco_falencia"],
    allow_negative=True,   # Z can be negative for highly distressed companies
    tooltip=(
        "Altman Z = 1.2×(WC/Ativo) + 1.4×(RE/Ativo) + 3.3×(EBIT/Ativo) "
        "+ 0.6×(MktCap/Passivo) + 1.0×(Vendas/Ativo). "
        ">2.99 seguro, 1.81-2.99 cinzento, <1.81 risco."
    ),
))
