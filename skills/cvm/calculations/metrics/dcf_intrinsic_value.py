"""metrics/dcf_intrinsic_value.py -- DCF (Discounted Cash Flow) Intrinsic Value.

[v2.1] 2-stage DCF model:
  Stage 1: 5Y explicit FCF projections using revenue_growth_1y as growth rate
  Stage 2: Terminal Value using IPCA (Brazilian inflation) as perpetual growth

Formula:
  Intrinsic Value = Σ (FCF_t / (1+WACC)^t) + TV / (1+WACC)^5
  TV = FCF_5 × (1+g_terminal) / (WACC - g_terminal)
  Per Share = Intrinsic Value / Shares

Inputs (all exist as engines/metrics):
  - FCF = operating_cf_at + investing_cf_at (TTM, cached)
  - WACC = wacc_at (CAPM-based, with Selic + Beta fallbacks)
  - Shares = shares_at (FRE + investsite fallback)
  - Growth = revenue_growth_1y (actual TTM YoY growth)
  - Terminal growth = IPCA 12M accumulated (from BCB SGS series 433)
  - Price = price_at (COTAHIST)

Returns:
  - dcf_intrinsic_value_at(): intrinsic value PER SHARE (BRL)
  - dcf_margin_of_safety: (intrinsic - price) / intrinsic (fraction)
  - History not supported (point-in-time only — too many assumptions for series)

Interpretation:
  - Margin of Safety > 0.25 (25%): undervalued (buy signal per Graham)
  - 0 < MoS < 0.25: fairly valued
  - MoS < 0: overvalued
"""
from __future__ import annotations

from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
from skills.cvm.calculations.engines.shares import shares_at
from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.engines.dre.revenue import revenue_at
from skills.cvm.calculations.metrics.wacc import wacc_at
from skills.cvm.calculations.metrics.revenue_growth import revenue_growth_1y_at
from skills.cvm.calculations.growth_helpers import get_terminal_growth, project_fcf, PROJECTION_YEARS
from skills.cvm.calculations._registry import MetricSpec, register_metric


def dcf_intrinsic_value_at(company: str, date: str) -> float | None:
    """Compute DCF Intrinsic Value per share at a specific date.

    2-stage model:
      Stage 1: 5Y explicit FCF projections (growth = revenue_growth_1y)
      Stage 2: Terminal Value (growth = IPCA 12M, capped at 8%)

    Returns:
        Intrinsic value PER SHARE in BRL, or None if:
        - FCF, WACC, or shares unavailable
        - WACC <= terminal growth (terminal value undefined)
        - FCF <= 0 (can't project from negative FCF)
    """
    # Get TTM FCF
    fco = operating_cf_at(company, date)
    fci = investing_cf_at(company, date)
    if fco is None or fci is None:
        return None
    base_fcf = fco + fci
    if base_fcf <= 0:
        return None  # Can't project from negative FCF

    # Get WACC (discount rate)
    wacc = wacc_at(company, date)
    if wacc is None or wacc <= 0:
        return None

    # Get growth rate (revenue_growth_1y, actual)
    growth_rate = revenue_growth_1y_at(company, date)
    if growth_rate is None:
        growth_rate = 0.05  # Default 5% if growth unavailable

    # Get terminal growth (IPCA 12M)
    terminal_growth = get_terminal_growth()

    # WACC must be > terminal growth for terminal value to be finite
    if wacc <= terminal_growth:
        return None

    # Get shares outstanding
    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    # Stage 1: Project FCF for 5 years
    fcf_projections = project_fcf(base_fcf, growth_rate, PROJECTION_YEARS)

    # Discount Stage 1 cash flows
    pv_stage1 = 0.0
    for t, fcf_t in enumerate(fcf_projections, 1):
        pv_stage1 += fcf_t / (1.0 + wacc) ** t

    # Stage 2: Terminal Value
    fcf_terminal = fcf_projections[-1] * (1.0 + terminal_growth)
    tv = fcf_terminal / (wacc - terminal_growth)
    pv_tv = tv / (1.0 + wacc) ** PROJECTION_YEARS

    # Intrinsic Value = PV(Stage 1) + PV(Terminal Value)
    intrinsic_value = pv_stage1 + pv_tv

    # Per share
    return intrinsic_value / shares


def dcf_margin_of_safety_at(company: str, date: str) -> float | None:
    """Compute Margin of Safety = (Intrinsic Value - Price) / Intrinsic Value.

    Returns:
        Margin of Safety as a fraction (0.25 = 25% undervalued), or None.
        Positive = undervalued, Negative = overvalued.
    """
    intrinsic = dcf_intrinsic_value_at(company, date)
    if intrinsic is None or intrinsic <= 0:
        return None

    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    return (intrinsic - price) / intrinsic


def dcf_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """DCF history is not supported — too many assumptions for a time series.

    DCF depends on WACC (which depends on daily Selic + Beta), FCF (quarterly),
    shares (annual), and IPCA (monthly). Computing it for 5Y of daily dates
    would be extremely expensive and the assumptions change daily.

    Returns empty list.
    """
    return []


# -- Register with the metric registry ----------------------------------------

register_metric(MetricSpec(
    name="dcf_intrinsic_value",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="DCF Valor Intrínseco",
    ratio_key="dcf_intrinsic_value",
    ratio_fn=dcf_intrinsic_value_at,
    history_fn=dcf_history,
    engines=["operating_cf", "investing_cf", "shares", "price", "revenue"],
    category="valuation",
    aliases=["dcf", "intrinsic_value", "valor_intrinseco"],
    tooltip="DCF = Σ FCF/(1+WACC)^t + TV. Valor intrínseco por ação. Margem de segurança vs preço atual.",
))

register_metric(MetricSpec(
    name="dcf_margin_of_safety",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="DCF Margem de Segurança",
    ratio_key="dcf_margin_of_safety",
    ratio_fn=dcf_margin_of_safety_at,
    history_fn=dcf_history,
    engines=["operating_cf", "investing_cf", "shares", "price", "revenue"],
    category="valuation",
    aliases=["margin_of_safety", "mos"],
    allow_negative=True,
    tooltip="Margem de Segurança = (Valor Intrínseco - Preço) / Valor Intrínseco. >25% subavaliado, <0 supervalorizado.",
))
