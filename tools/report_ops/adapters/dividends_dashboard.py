"""adapters/dividends_dashboard.py — Dividends dashboard adapter.

Takes a dividends.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<dividends dashboard result>,
         config={"adapter": "dividends_dashboard"})

Tabs produced (already shaped by dividends.dashboard() in
skills/cvm/dividends/modes/dashboard.py):
  - Overview:   Summary text section (company, ticker, events count, years)
  - History:    recent B3 dividend events table (date, type, value per share,
                related-to)
  - Annual:     DVA 7.08.04.* per fiscal year table (year, Dividendos, JCP,
                Total Remuneração)

KPI cards (top-level):
  Total Dividends Paid, Dividend Yield, Payout Ratio, Last Payment Date —
  values pre-formatted as BRL/pct/text via apply_fmt.

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
# Each dividends.dashboard() KPI carries a `unit` ("BRL", "pct", "date") that
# tells us how to format the value. Map each unit to a format spec understood
# by tools.report_ops.formats.apply_fmt(). Falls back to "text" for unknown
# units so the KPI still renders (just without compact formatting).
_UNIT_TO_SPEC = {
    "BRL":     "brl",
    "pct":     "pct",     # Dividends stores pct values as fractions (0.12 = 12%)
    "ratio":   "pct",
    "num":     "num",
    "int":     "int",
    "date":    "text",    # ISO date strings (YYYY-MM-DD) pass through as text
    "text":    "text",
}


def _format_kpi(k: dict) -> dict:
    """Convert a dividends.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "Total Dividends Paid", "value": "R$ 50,00 B", "unit": "BRL"}
            (value may already be pre-formatted by report.py -- if so, pass
            through unchanged when it's already a string.)
    Output: {"label": "Total Dividends Paid", "value": "R$ 50,00 B", "format": "brl"}
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

@register_adapter("dividends_dashboard")
def dividends_dashboard(result: dict) -> dict:
    """Flatten dividends.dashboard() result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from dividends.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data
    correctly. KPI cards are re-formatted via the unit -> spec map.
    """
    if not _ok(result):
        return _error_table(result, title="Dividends Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Dividends Dashboard")

    # Format the top-level KPI cards (each KPI carries a `unit` -> format spec).
    kpis_in = result.get("kpis") or []
    kpis_out = [_format_kpi(k) for k in kpis_in]

    # [v3] Preserve `group` field on tabs so the dashboard sidebar can render
    # grouped navigation (Resumo / Proventos).
    tabs_out: list[dict] = []
    for tab in tabs_in:
        tab_out = {
            "name": tab.get("name", ""),
            "sections": tab.get("sections", []),
        }
        if tab.get("group"):
            tab_out["group"] = tab["group"]
        tabs_out.append(tab_out)

    return {
        "company": result.get("company", ""),
        "company_header": result.get("company_header", {}),
        "tabs": tabs_out,
        "kpis": kpis_out,
        "sources": [],
        "freshness_footer": result.get("freshness_footer", ""),
    }
