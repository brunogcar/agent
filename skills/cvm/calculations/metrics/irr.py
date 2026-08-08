"""metrics/irr.py -- IRR (Internal Rate of Return) / TIR (Taxa Interna de Retorno).

[v2.1] IRR is the discount rate that makes NPV = 0 for a series of cash flows.

For stock valuation:
  CF_0 = -Price (buy the stock today)
  CF_1..CF_5 = Projected FCF (5Y, using revenue_growth_1y)
  CF_6 = Terminal Value (FCF_5 × (1+g) / (r-g)) -- but r is the unknown!

Since terminal value depends on r, this is a fixed-point problem. We solve it
using bisection (guaranteed convergence, no derivative needed).

What IRR means for stocks:
  "If I buy at today's price and the company's FCF grows as projected, what's
   my annualized return over 5Y + terminal sale?"
  - IRR > WACC: stock is undervalued (returns exceed cost of capital)
  - IRR < WACC: stock is overvalued (returns below cost of capital)
  - IRR > 15%: attractive investment
  - IRR < 10%: marginal

Inputs (all exist):
  - Price = price_at (COTAHIST)
  - FCF = operating_cf_at + investing_cf_at (TTM, cached)
  - Growth = revenue_growth_1y (actual)
  - Terminal growth = IPCA 12M (same as DCF)
  - Shares = shares_at (for per-share terminal value)

Returns:
  IRR as a fraction (0.15 = 15% annualized return), or None.
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
from skills.cvm.calculations.engines.shares import shares_at
from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.metrics.revenue_growth import revenue_growth_1y_at
from skills.cvm.calculations.metrics.wacc import wacc_at
from skills.cvm.calculations.growth_helpers import get_terminal_growth, project_fcf, PROJECTION_YEARS
from skills.cvm.calculations._registry import MetricSpec, register_metric


def _npv(rate: float, cash_flows: list[float]) -> float:
    """Compute NPV of a series of cash flows at a given discount rate.

    CF_0 is at t=0 (not discounted), CF_1 at t=1, etc.
    """
    npv = 0.0
    for t, cf in enumerate(cash_flows):
        npv += cf / (1.0 + rate) ** t
    return npv


def _solve_irr(
    price: float,
    fcf_projections: list[float],
    terminal_growth: float,
    shares: float,
) -> float | None:
    """Solve for IRR using bisection method.

    The cash flows are:
      CF_0 = -Price (buy)
      CF_1..CF_5 = fcf_projections[0..4]
      CF_6 = Terminal Value = fcf_projections[-1] × (1+g) / (r-g) / shares

    But terminal value depends on r (the IRR we're solving for), so we
    compute NPV(r) and bisect until NPV ≈ 0.

    The per-share terminal value = TV_total / shares, and we add it to CF_5
    (the last projection year) as a combined cash flow.

    Returns IRR as a fraction, or None if no solution found.
    """
    # Per-share FCF projections
    fcf_per_share = [f / shares for f in fcf_projections]

    def npv_at_r(r: float) -> float:
        """NPV at rate r. CF_0 = -price, CF_1..5 = fcf_per_share, CF_5 += TV."""
        if r <= terminal_growth:
            return float('inf')  # Terminal value undefined

        # Terminal value per share
        tv_per_share = (fcf_per_share[-1] * (1.0 + terminal_growth)) / (r - terminal_growth)

        # Cash flows: -price, fcf_1, fcf_2, ..., fcf_5 + tv
        cash_flows = [-price] + fcf_per_share[:-1] + [fcf_per_share[-1] + tv_per_share]
        return _npv(r, cash_flows)

    # Bisection: find r where NPV(r) = 0
    # At r=0: NPV = sum of all CFs (likely positive if FCF > 0)
    # At r=1 (100%): NPV ≈ -price (likely negative)
    lo, hi = 0.001, 1.0  # 0.1% to 100%
    npv_lo = npv_at_r(lo)
    npv_hi = npv_at_r(hi)

    if npv_lo < 0:
        # Even at 0.1% discount, NPV is negative → stock is overvalued at any rate
        return None
    if npv_hi > 0:
        # Even at 100% discount, NPV is positive → extremely undervalued
        return 1.0  # Cap at 100%

    # Bisection — 100 iterations = precision to 1e-30
    for _ in range(100):
        mid = (lo + hi) / 2.0
        npv_mid = npv_at_r(mid)
        if abs(npv_mid) < 1e-6:
            return mid
        if npv_mid > 0:
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2.0


def irr_at(company: str, date: str) -> float | None:
    """Compute IRR (Internal Rate of Return) for a stock investment.

    "If I buy at today's price and FCF grows as projected, what's my
    annualized return over 5Y + terminal sale?"

    Returns:
        IRR as a fraction (0.15 = 15%), or None if:
        - FCF, price, or shares unavailable
        - FCF <= 0 (can't project from negative FCF)
        - No solution found (stock overvalued at any discount rate)
    """
    # Get TTM FCF
    fco = operating_cf_at(company, date)
    fci = investing_cf_at(company, date)
    if fco is None or fci is None:
        return None
    base_fcf = fco + fci
    if base_fcf <= 0:
        return None

    # Get price (current market price)
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    # Get growth rate
    growth_rate = revenue_growth_1y_at(company, date)
    if growth_rate is None:
        growth_rate = 0.05

    # Get terminal growth (IPCA)
    terminal_growth = get_terminal_growth()

    # Get shares
    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    # Project FCF for 5 years
    fcf_projections = project_fcf(base_fcf, growth_rate, PROJECTION_YEARS)

    # Solve for IRR
    return _solve_irr(price, fcf_projections, terminal_growth, shares)


def irr_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """IRR history not supported — same reasoning as DCF."""
    return []


register_metric(MetricSpec(
    name="irr",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="TIR (IRR)",
    ratio_key="irr",
    ratio_fn=irr_at,
    history_fn=irr_history,
    engines=["operating_cf", "investing_cf", "shares", "price", "revenue"],
    category="valuation",
    aliases=["tir", "internal_rate_of_return", "taxa_interna_retorno"],
    allow_negative=True,
    tooltip="TIR = taxa de retorno anualizada se comprar ao preço atual. >WACC subavaliado, <WACC supervalorizado. >15% atrativo.",
))
