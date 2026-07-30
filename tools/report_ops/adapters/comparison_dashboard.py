"""adapters/comparison_dashboard.py — Comparison dashboard adapter.

Takes a comparison.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<comparison dashboard result>,
         config={"adapter": "comparison_dashboard"})

Tabs produced (already shaped by comparison.dashboard() in
skills/cvm/comparison/modes/dashboard.py):
  - Overview:     Compared Tickers table (ticker + sector) + per-ticker
                  errors (if any)
  - Valuation:    side-by-side valuation ratios table (all tickers × metrics)
  - Financials:   side-by-side financial metrics table (latest annual)
  - Dividends:    side-by-side dividend metrics table
  - Growth:       QoQ + YoY + TTM ratios growth table

KPI cards (top-level):
  Cheapest P/L, Best ROE, Best Div Yield, Cheapest EV/EBITDA — values
  pre-formatted as "<ticker> (<formatted>)" via apply_fmt.

This adapter is THIN — the dashboard mode already produces the tab
structure in the canonical dashboard shape. The adapter only:
  1. Pulls top-level KPIs (re-formatting them via the unit -> spec map).
  2. Passes tabs through verbatim (sections are already typed: text /
     chart / table).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)


# ── KPI formatting ───────────────────────────────────────────────────────────
# Each comparison.dashboard() KPI carries a `unit` ("pct", "num") that tells us
# how to format the value. Map each unit to a format spec understood by
# tools.report_ops.formats.apply_fmt(). Falls back to "text" for unknown
# units so the KPI still renders (just without compact formatting).
_UNIT_TO_SPEC = {
    "pct":     "pct",        # Comparison stores pct values as fractions (0.12 = 12%)
    "num":     "num",
    "int":     "int",
    "BRL":     "brl",
    "ratio":   "pct",
    "x":       "num",
}


def _format_kpi(k: dict) -> dict:
    """Convert a comparison.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "Cheapest P/L", "value": "VALE3 (6.50)", "unit": "num"}
            (value may already be pre-formatted by report.py -- if so, pass
            through unchanged when it's already a string.)
    Output: {"label": "Cheapest P/L", "value": "VALE3 (6.50)", "format": "num"}
    """
    from tools.report_ops.formats import apply_fmt

    label = k.get("label", "")
    value = k.get("value")
    unit = (k.get("unit") or "").strip()
    spec = _UNIT_TO_SPEC.get(unit, "text")

    # If the value is already a string (pre-formatted by report.py), keep
    # it verbatim -- the dashboard mode already called apply_fmt. Only
    # re-format raw numbers.
    if isinstance(value, str):
        formatted = value
    else:
        try:
            formatted = apply_fmt(_safe_num(value), spec)
        except Exception:
            formatted = str(value) if value is not None else "—"

    return {
        "label": label,
        "value": formatted,
        "format": spec,
    }


# ── Adapter entry point ──────────────────────────────────────────────────────

@register_adapter("comparison_dashboard")
def comparison_dashboard(result: dict) -> dict:
    """Flatten comparison.dashboard() result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from comparison.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data
    correctly. KPI cards are re-formatted via the unit -> spec map.
    """
    if not _ok(result):
        return _error_table(result, title="Comparison Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Comparison Dashboard")

    # Format the top-level KPI cards (each KPI carries a `unit` -> format spec).
    kpis_in = result.get("kpis") or []
    kpis_out = [_format_kpi(k) for k in kpis_in]

    return {
        "company": " vs ".join(result.get("tickers") or []),
        "tabs": tabs_in,
        "kpis": kpis_out,
        "sources": [],
    }
