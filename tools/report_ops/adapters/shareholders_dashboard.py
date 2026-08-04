"""adapters/shareholders_dashboard.py — Shareholders dashboard adapter.

Takes a shareholders.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<shareholders dashboard result>,
         config={"adapter": "shareholders_dashboard"})

Tabs produced (already shaped by shareholders.dashboard() in
skills/cvm/shareholders/modes/dashboard.py):
  - Overview:          Summary text section (company, data de referência,
                       % free float, total acionistas, PL total)
  - Top Shareholders:  table of top 5 named shareholders (Acionista,
                       % Total, Qtde Total, Controlador)
  - Free Float:        single-row table (% Free Float, Acionistas PF,
                       Acionistas PJ, Acionistas Inst.)
  - Equity Structure:  table of BPP 2.03.* components (Componente, Valor BRL)

KPI cards (top-level):
  % Free Float, Total Acionistas, PL Total — values pre-formatted as
  pct_raw / int / brl via apply_fmt.

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
# Each shareholders.dashboard() KPI carries a `unit` ("pct_raw", "int", "brl",
# "pct", "num", "text") that tells us how to format the value. Map each unit to
# a format spec understood by tools.report_ops.formats.apply_fmt(). Falls back
# to "text" for unknown units so the KPI still renders (just without compact
# formatting).
_UNIT_TO_SPEC = {
    "pct_raw": "pct_raw",  # FRE ownership %: 71.1 = 71.1% (already in percent units)
    "pct":     "pct",      # fraction: 0.711 = 71.1%
    "num":     "num",
    "int":     "int",
    "text":    "text",
    "brl":     "brl",
}


def _format_kpi(k: dict) -> dict:
    """Convert a shareholders.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "% Free Float", "value": "71,10%", "unit": "pct_raw"}
            (value may already be pre-formatted by report.py -- if so, pass
            through unchanged when it's already a string.)
    Output: {"label": "% Free Float", "value": "71,10%", "format": "pct_raw"}
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

@register_adapter("shareholders_dashboard")
def shareholders_dashboard(result: dict) -> dict:
    """Flatten shareholders.dashboard() result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from shareholders.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data
    correctly. KPI cards are re-formatted via the unit -> spec map.
    """
    if not _ok(result):
        return _error_table(result, title="Shareholders Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Shareholders Dashboard")

    # Format the top-level KPI cards (each KPI carries a `unit` -> format spec).
    kpis_in = result.get("kpis") or []
    kpis_out = [_format_kpi(k) for k in kpis_in]

    # [v3] Preserve `group` field on tabs so the dashboard sidebar can render
    # grouped navigation (Resumo / Acionistas / Estrutura).
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
