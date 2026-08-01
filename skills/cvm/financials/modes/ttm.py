"""Mode: ttm -- rolling TTM (anualizado) time series.

For each historical quarter-end date, computes TTM (trailing twelve months)
values using the existing `compute_ttm_with_engines()` — flow metrics via
calculations engines (revenue_at, ebit_at, etc.), snapshot metrics via
4-quarter averaging. Produces a time series with ~4 data points per year,
deseasonalized.

This is the "Anualiz" tab from the user's private spreadsheet — rolling
TTM recomputed at every quarter boundary, so you can chart trends without
quarterly noise.

Registered as "ttm" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.modes.quarterly import quarterly
from skills.cvm.financials.metrics import compute_ttm_with_engines


# Maps a quarter number (1-4) to its calendar end-date suffix (MM-DD).
_QUARTER_END_SUFFIX = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


@register_mode(
    "ttm",
    description=(
        "Rolling TTM (anualizado) time series. For each historical quarter, "
        "computes trailing-12-months values via calculations engines. "
        "Deseasonalizes flow metrics (DRE/DFC) — 4 data points per year "
        "with quarterly noise smoothed. Default: 8 TTM periods (2 years)."
    ),
    params={
        "company":     "str. B3 ticker (PETR4), name, or CNPJ. Required.",
        "periods":     "int. Number of TTM periods to return. Default: 8.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="ttm", params=\'{"company":"PETR4"}\')',
    ],
)
def ttm(company: str = "", periods: int = 8, consolidado: int = 1) -> dict:
    """Rolling TTM (anualizado) time series.

    For each historical quarter-end date, computes TTM values:
      - Flow metrics (revenue, EBIT, D&A, earnings, FCO/FCI/FCF, EBITDA):
        via calculations engines (TTM derivation at that date)
      - Snapshot metrics (ativo_total, caixa, PL, divida_bruta):
        4-quarter average at that date (same as compute_ttm_with_engines)
      - Ratios (margins, ROA/ROE, debt ratios): computed from TTM metrics

    Skips quarters with fewer than 4 quarters of history behind them
    (can't compute TTM). The first TTM data point appears at the 4th
    quarter of available history.

    Args:
        company: Ticker, name, or CNPJ.
        periods: Number of TTM periods to return. Default: 8 (2 years).
        consolidado: 1=consolidated (default), 0=individual.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "periods": [...]}``
        where each period is ``{"period_range", "ttm_date", "metrics",
        "ratios"}``. The periods are sorted oldest-first.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[financials] TTM: Fetching quarterly data for {company}...", flush=True)

    # Fetch enough quarters to compute `periods` TTM data points.
    # Need `periods + 3` quarters (first 3 can't produce TTM).
    quarters_needed = periods + 3
    qrt = quarterly(company=company, periods=quarters_needed, consolidado=consolidado)
    if qrt.get("status") != "ok":
        return qrt

    all_quarters = qrt.get("periods") or []
    if len(all_quarters) < 4:
        return {"status": "insufficient_data",
                "error": f"Need 4+ quarters for TTM, got {len(all_quarters)}"}

    print(f"[financials] TTM: Computing TTM for {len(all_quarters) - 3} periods...", flush=True)

    ttm_periods: list[dict] = []
    # Iterate from the 4th quarter onward (first 3 can't produce TTM)
    for i in range(3, len(all_quarters)):
        if len(ttm_periods) >= periods:
            break

        # Quarters up to and including position i (oldest-first)
        window = all_quarters[:i + 1]
        latest = window[-1]
        year = latest.get("year")
        qnum = latest.get("quarter")

        if year is None or qnum not in _QUARTER_END_SUFFIX:
            continue

        ttm_date = f"{year}-{_QUARTER_END_SUFFIX[qnum]}"

        print(f"[financials] TTM:   {latest.get('period', '?')} (date={ttm_date})...", flush=True, end="")

        try:
            ttm_result = compute_ttm_with_engines(company, ttm_date, window)
            if ttm_result.get("status") == "ok":
                ttm_periods.append({
                    "period_range": ttm_result.get("period_range", ""),
                    "ttm_date": ttm_date,
                    "quarter": latest.get("period", ""),
                    "metrics": ttm_result.get("metrics", {}),
                    "ratios": ttm_result.get("ratios", {}),
                })
                print(" done.", flush=True)
            else:
                print(" skipped (insufficient).", flush=True)
        except Exception as e:
            print(f" error: {e}", flush=True)

    print(f"[financials] TTM: Done! {len(ttm_periods)} TTM periods.", flush=True)

    return {
        "status": "ok",
        "company": company,
        "periods": ttm_periods,
    }
