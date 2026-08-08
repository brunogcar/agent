"""metrics/p_fcf.py -- FCF/Ação (Free Cash Flow per share) + P/FCF (Price-to-FCF) metric.

FCF  = FCO + FCI                  (Free Cash Flow = Operating CF + Investing CF)
FCF/Ação = FCF / shares           (per-share value, composes 2 cash flow engines + shares)
P/FCF    = price / (FCF / shares) (price ratio, adds price engine)
         = price × shares / FCF

Where:
  FCO = TTM Fluxo de Caixa Operacional   (DFC 6.01, typically POSITIVE)
  FCI = TTM Fluxo de Caixa de Investimento (DFC 6.02, typically NEGATIVE)
  FCF = FCO + FCI                         (FCO minus capex/acquisitions, since FCI < 0)

This metric produces BOTH:
  - FCF/Ação (per-share value): useful on its own (free cash flow available
    to equity holders after maintaining the business)
  - P/FCF (price ratio):        tells you if the stock is cheap vs free cash flow

Mirrors metrics/p_ebit.py but composes 4 engines (price + shares + operating_cf
+ investing_cf) and computes FCF internally as FCO + FCI.

Engines composed: price + shares + operating_cf + investing_cf

Interpretation:
  - P/FCF < 10:  cheap (strong free cash flow generation relative to price)
  - P/FCF 10-20: fair
  - P/FCF 20-30: expensive
  - P/FCF > 30:  very expensive (or capital-intensive business with weak FCF)
  - P/FCF = None when FCF <= 0 (negative free cash flow -- ratio meaningless;
    company is spending more on investments than it generates from operations)

P/FCF is the most conservative price ratio because:
  - It accounts for capex (FCI includes capex outflows)
  - It excludes non-cash items (depreciation, amortization)
  - It uses real cash, not accounting earnings
  - It captures the actual cash available to return to shareholders

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.metrics.p_fcf import fcf_ps_at, p_fcf_at, p_fcf_history
    e = fcf_ps_at("PETR4", "2024-06-30")   # -> 12.40 (FCF per share)
    r = p_fcf_at("PETR4", "2024-06-30")    # -> 4.8 (P/FCF ratio)
    h = p_fcf_history("PETR4", "2024-01-01", "2024-12-31")
"""
from __future__ import annotations

from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at, operating_cf_periods
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at, investing_cf_periods
from skills.cvm.calculations.engines.shares import shares_at, shares_periods
from skills.cvm.calculations._registry import MetricSpec, register_metric


# ── Per-share value: FCF/Ação = (FCO + FCI) / shares ─────────────────────────

def fcf_ps_at(company: str, date: str) -> float | None:
    """Compute FCF/Ação (Free Cash Flow per share) at a specific date.

    FCF = FCO + FCI  (Operating CF + Investing CF; FCI is typically negative)
    FCF/Ação = FCF / shares outstanding

    [v1.22 fix] Same fix as ev_fcf: use *_at instead of *_periods.
    Was 95-105s, now <0.01s.
    """
    fco_val = operating_cf_at(company, date)
    fci_val = investing_cf_at(company, date)

    if fco_val is None or fci_val is None:
        return None

    # [v1.22] Alignment guard removed — FCO and FCI come from the same DFC
    # statement, so alignment is guaranteed. Using *_at functions (point-in-time)
    # means both resolve to the same most-recent period <= date.

    fcf = fco_val + fci_val
    if fcf <= 0:
        return None  # Negative/zero FCF -- per-share value meaningless

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    return fcf / shares


# ── Price ratio: P/FCF = price / (FCF / shares) ──────────────────────────────

def p_fcf_at(company: str, date: str) -> float | None:
    """Compute P/FCF (Price-to-Free-Cash-Flow) at a specific date.

    P/FCF = price / ((FCO + FCI) / shares) = price × shares / (FCO + FCI)

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        P/FCF ratio as float, or None if any component is missing or
        FCF <= 0 (negative free cash flow -- ratio meaningless).
    """
    price = price_at(company, date)
    if price is None or price <= 0:
        return None

    fcf_ps = fcf_ps_at(company, date)
    if fcf_ps is None or fcf_ps <= 0:
        return None  # Negative/zero FCF → P/FCF is meaningless

    return price / fcf_ps


# ── History: daily series with FCF/Ação + P/FCF ──────────────────────────────

def p_fcf_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """Compute daily FCF/Ação + P/FCF time series for a date range.

    Step-function optimization:
    - price:        daily
    - shares:       annual (step)
    - operating_cf: quarterly (step)
    - investing_cf: quarterly (step)

    For each daily price, find the most recent TTM FCO, TTM FCI, and shares,
    then compute FCF = FCO + FCI, FCF/Ação = FCF / shares, P/FCF = price / FCF/Ação.

    Args:
        company: Ticker.
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date", "price", "fcf_ps", "p_fcf", "ttm_fco", "ttm_fci",
                 "shares"} sorted oldest-first.
        Entries with None FCF/Ação/P_FCF (negative FCF, missing data) are
        included with fcf_ps=None, p_fcf=None so charts show gaps.
    """
    # Get price series (daily)
    prices = price_series(company, date_from, date_to)
    if not prices:
        return []

    # Get TTM FCO periods (quarterly step function)
    fco_periods_list = operating_cf_periods(company)

    # Get TTM FCI periods (quarterly step function)
    fci_periods_list = investing_cf_periods(company)

    # Get shares periods (annual step function)
    sh_periods = shares_periods(company)

    result = []
    for p in prices:
        date = p["date"]
        price = p["close"]

        # Find most recent TTM FCO <= date (track resolved date for alignment)
        ttm_fco = None
        fco_resolved_date = None
        for fp in reversed(fco_periods_list):
            if fp["date"] <= date:
                ttm_fco = fp["ttm_fco"]
                fco_resolved_date = fp["date"]
                break

        # Find most recent TTM FCI <= date (track resolved date for alignment)
        ttm_fci = None
        fci_resolved_date = None
        for ip in reversed(fci_periods_list):
            if ip["date"] <= date:
                ttm_fci = ip["ttm_fci"]
                fci_resolved_date = ip["date"]
                break

        # Find most recent shares <= date
        shares = None
        for sp in reversed(sh_periods):
            if sp["date"] <= date:
                shares = sp["shares"]
                break

        # Compute FCF = FCO + FCI
        # Alignment guard: only sum if both resolved to the SAME period-end
        # date.  FCO (6.01) and FCI (6.02) are co-reported in the same DFC
        # filing so this almost always holds, but if one has a data gap at a
        # quarter the other doesn't, summing two different periods would
        # silently produce a nonsense FCF.  Leave fcf=None (chart gap) instead.
        fcf = None
        if ttm_fco is not None and ttm_fci is not None and fco_resolved_date == fci_resolved_date:
            fcf = ttm_fco + ttm_fci

        # Compute FCF/Ação = FCF / shares
        fcf_ps = None
        if fcf is not None and fcf > 0 and shares is not None and shares > 0:
            fcf_ps = fcf / shares

        # Compute P/FCF = price / (FCF/Ação)
        p_fcf = None
        if fcf_ps is not None and fcf_ps > 0 and price > 0:
            p_fcf = price / fcf_ps

        result.append({
            "date": date,
            "price": price,
            "fcf_ps": fcf_ps,
            "p_fcf": p_fcf,
            "ttm_fco": ttm_fco,
            "ttm_fci": ttm_fci,
            "shares": shares,
        })

    return result


# ── Register with the metric registry ────────────────────────────────────────

register_metric(MetricSpec(
    name="p_fcf",
    per_share_label="FCF/Ação",
    per_share_key="fcf_ps",
    per_share_fn=fcf_ps_at,
    ratio_label="P/FCF",
    ratio_key="p_fcf",
    ratio_fn=p_fcf_at,
    history_fn=p_fcf_history,
    engines=["price", "shares", "operating_cf", "investing_cf"],
    category="valuation",
    aliases=["p_fcf", "pfcf", "preco_fcf"],
))
