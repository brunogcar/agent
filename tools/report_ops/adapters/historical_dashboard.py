"""adapters/historical_dashboard.py — Historical dashboard adapter.

Takes a historical.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<historical dashboard result>,
         config={"adapter": "historical_dashboard"})

Tabs produced (already shaped by historical.dashboard() in
skills/cvm/historical/modes/dashboard.py):
  - Overview:             Summary text section (company + per-metric status)
  - Percentile Analysis:  table showing min/25th/median/75th/max/current/
                          percentile/interpretation per metric
  - Trend:                table showing current + 1Y/3Y averages + 1Y/3Y
                          change per metric

KPI cards (top-level):
  P/L, P/VPA, EV/EBITDA, ROE, ROIC, Div Yield — values pre-formatted as
  num/pct via apply_fmt.

This adapter is THIN — the dashboard mode already produces the tab
structure in the canonical dashboard shape. The adapter only:
  1. Pulls top-level KPIs (re-formatting them via the unit -> spec map).
  2. Passes tabs through verbatim (sections are already typed: text /
     table).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)


# ── KPI formatting ───────────────────────────────────────────────────────────
# Each historical.dashboard() KPI carries a `unit` ("ratio" or "pct") that
# tells us how to format the value. Map each unit to a format spec understood
# by tools.report_ops.formats.apply_fmt(). Falls back to "text" for unknown
# units so the KPI still renders (just without compact formatting).
_UNIT_TO_SPEC = {
    "ratio":   "num",     # Price multiples (P/L, P/VPA, EV/EBITDA) shown as raw numbers
    "pct":     "pct",     # Profitability/yield ratios stored as fractions (0.185 = 18.5%)
    "num":     "num",
    "int":     "int",
    "text":    "text",
}


def _format_kpi(k: dict) -> dict:
    """Convert a historical.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "P/L", "value": "5,23", "unit": "ratio"}
            (value may already be pre-formatted by report.py -- if so, pass
            through unchanged when it's already a string.)
    Output: {"label": "P/L", "value": "5,23", "format": "num"}
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

@register_adapter("historical_dashboard")
def historical_dashboard(result: dict) -> dict:
    """Flatten historical.dashboard() result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from historical.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data
    correctly. KPI cards are re-formatted via the unit -> spec map.
    """
    if not _ok(result):
        return _error_table(result, title="Historical Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Historical Dashboard")

    # Format the top-level KPI cards (each KPI carries a `unit` -> format spec).
    kpis_in = result.get("kpis") or []
    kpis_out = [_format_kpi(k) for k in kpis_in]

    return {
        "company": result.get("company", ""),
        "tabs": tabs_in,
        "kpis": kpis_out,
        "sources": [],
    }
