"""adapters/screener_dashboard.py — Screener dashboard adapter.

Takes a screener.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<screener dashboard result>,
         config={"adapter": "screener_dashboard"})

Tabs produced (already shaped by screener.dashboard() in
skills/cvm/screener/modes/dashboard.py):
  - Overview:    Summary text section (setor, peer_count, ticker being
                 compared, cheap/expensive labels summary)
  - Peers:       full peers table (Ticker, Preço, Market Cap, P/L, P/VPA,
                 EV/EBITDA, ROE, Div Yield, Receita Líquida, EBITDA,
                 Marg. EBITDA, Cresc. Receita, Segmento)
  - Comparison:  per-metric my vs sector table (Metric, My Value,
                 Sector Median, Delta %, vs Sector)

KPI cards (top-level):
  Median P/L, Median P/VPA, Median EV/EBITDA, Median ROE, Median Div Yield
  — values pre-formatted as num/pct via apply_fmt.

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
# Each screener.dashboard() KPI carries a `unit` ("num", "pct", "text") that
# tells us how to format the value. Map each unit to a format spec understood
# by tools.report_ops.formats.apply_fmt(). Falls back to "text" for unknown
# units so the KPI still renders (just without compact formatting).
_UNIT_TO_SPEC = {
    "pct":  "pct",    # ROE + Div Yield stored as fractions (0.185 = 18.5%)
    "num":  "num",    # P/L, P/VPA, EV/EBITDA shown as raw multiples
    "int":  "int",
    "text": "text",
    "brl":  "brl",    # not currently used by screener KPIs but kept for symmetry
}


def _format_kpi(k: dict) -> dict:
    """Convert a screener.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "Median P/L", "value": "8,50", "unit": "num"}
            (value may already be pre-formatted by report.py -- if so, pass
            through unchanged when it's already a string.)
    Output: {"label": "Median P/L", "value": "8,50", "format": "num"}
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

@register_adapter("screener_dashboard")
def screener_dashboard(result: dict) -> dict:
    """Flatten screener.dashboard() result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from screener.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data
    correctly. KPI cards are re-formatted via the unit -> spec map.
    """
    if not _ok(result):
        return _error_table(result, title="Screener Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Screener Dashboard")

    # Format the top-level KPI cards (each KPI carries a `unit` -> format spec).
    kpis_in = result.get("kpis") or []
    kpis_out = [_format_kpi(k) for k in kpis_in]

    return {
        "company": result.get("company", ""),
        "tabs": tabs_in,
        "kpis": kpis_out,
        "sources": [],
    }
