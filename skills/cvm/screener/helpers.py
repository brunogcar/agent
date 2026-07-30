"""skills/cvm/screener/helpers.py — Internal helpers for screener modes.

Four helpers used by both the sector() and compare() modes:

  - _roe_from_ratios(ratios)        -> extract ROE from valuation ratios
  - _pct_change(curr, prev)         -> YoY % change (None on missing/sign-change)
  - _compute_medians(peers)         -> sector medians dict from peers list
  - _build_comparison(my_data, med) -> per-metric comparison: my vs sector

These are NOT public modes — they're internal plumbing shared between
sector.py (which computes medians + peer table) and compare.py (which
reuses _build_comparison to classify cheap/expensive).

[v1.2] _roe_from_ratios() simplified to `ratios.get("roe")` (was
lucro_liquido/patrimonio_liquido division — that derivation was dead code
in production because valuation.ratios() doesn't reliably populate those
keys; they live in financials.summary instead).
"""
from __future__ import annotations

from statistics import median


def _roe_from_ratios(ratios: dict) -> float | None:
    """Extract ROE from valuation ratios.

    [v1.2] Since Phase 2B, valuation.ratios() returns ``roe`` directly
    (computed by calculations.metrics.roe_at — TTM earnings / equity snapshot).
    The previous version tried to derive ROE from lucro_liquido /
    patrimonio_liquido in the ratios dict, but those keys are NOT reliably
    populated in valuation's output (they live in financials.summary instead).
    The simplified version just reads the canonical key.
    """
    return ratios.get("roe")


def _pct_change(curr: float | None, prev: float | None) -> float | None:
    """Compute % change = (curr - prev) / |prev|. None on missing/negative/sign-change."""
    if curr is None or prev is None:
        return None
    if prev <= 0:
        return None
    if curr * prev < 0:
        return None
    return (curr - prev) / abs(prev)


def _compute_medians(peers: list[dict]) -> dict:
    """Compute sector medians from peers list.

    [v1.2] Added roa, margem_liquida, divida_pl (sourced from valuation.ratios
    via calculations metrics). Backward-compat preserved — all v1.1 keys
    (p_l, p_vpa, ev_ebitda, roe, dividend_yield, market_cap) still present.
    """
    def _median(key: str) -> float | None:
        vals = [p.get(key) for p in peers if p.get(key) is not None]
        return median(vals) if vals else None

    return {
        "p_l": _median("p_l"),
        "p_vpa": _median("p_vpa"),
        "ev_ebitda": _median("ev_ebitda"),
        "roe": _median("roe"),
        "dividend_yield": _median("dividend_yield"),
        "market_cap": _median("market_cap"),
        # [v1.2] New — from calculations metrics via valuation.ratios
        "roa": _median("roa"),
        "margem_liquida": _median("margem_liquida"),
        "divida_pl": _median("divida_pl"),
    }


def _build_comparison(my_data: dict, medians: dict) -> dict:
    """Build a per-metric comparison: my value vs sector median + delta %.

    [v1.2] Added roa, margem_liquida, divida_pl. Classification:
      - "cheap"/"expensive" — valuation multiples where lower = cheaper
        (p_l, p_vpa, ev_ebitda, divida_pl — lower debt-to-equity = less
        leveraged = "cheaper" risk profile).
      - "above"/"below" — quality metrics where higher = better
        (roe, roa, margem_liquida, dividend_yield).
    """
    valuation_multiples = ("p_l", "p_vpa", "ev_ebitda", "divida_pl")
    quality_metrics = ("roe", "dividend_yield", "roa", "margem_liquida")
    metrics = list(valuation_multiples) + list(quality_metrics)
    out = {}
    for m in metrics:
        my_val = my_data.get(m)
        med_val = medians.get(m)
        entry = {"my_value": my_val, "sector_median": med_val}
        if my_val is not None and med_val is not None and med_val != 0:
            entry["delta_pct"] = (my_val - med_val) / abs(med_val)
            # Interpretation: for valuation multiples + leverage — below median
            # = "cheap" (or "less leveraged" for divida_pl). For quality
            # metrics — above median = "above".
            if m in valuation_multiples:
                entry["vs_sector"] = "cheap" if my_val < med_val else "expensive"
            elif m in quality_metrics:
                entry["vs_sector"] = "above" if my_val > med_val else "below"
        else:
            entry["delta_pct"] = None
            entry["vs_sector"] = "n/a"
        out[m] = entry
    return out
