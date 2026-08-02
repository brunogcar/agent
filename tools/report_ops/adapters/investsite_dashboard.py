"""adapters/investsite_dashboard.py — Investsite dashboard adapter.

Takes an investsite.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<investsite dashboard result>,
         config={"adapter": "investsite_dashboard"})

Tabs produced (already shaped by investsite.dashboard() in
skills/investsite/modes/dashboard.py):
  - Overview:        Summary text section (ticker, company, P/L, P/VPA,
                     EV/EBITDA, ROE, Dividend Yield)
  - Key Indicators:  2-column [Indicador, Valor] table flattening
                     precos_relativos + retornos_margens (P/L, P/VPA,
                     EV/EBITDA, Dividend Yield, ROE, ROA, Margem EBITDA,
                     Margem Líquida)
  - Latest Events:   4-column [Data, Categoria, Descrição, Link] table of
                     the 10 most recent Fato Relevante events with direct
                     CVM rad.cvm.gov.br PDF links

KPI cards (top-level):
  P/L, P/VPA, EV/EBITDA (num), ROE, Dividend Yield (pct) — values
  pre-formatted via apply_fmt.

This adapter is THIN — the dashboard mode already produces the tab
structure in the canonical dashboard shape. The adapter only:
  1. Pulls top-level KPIs (re-formatting them via the unit -> spec map).
  2. Passes tabs through verbatim (sections are already typed: text /
     table).

[v1.1] NEW — added as part of the investsite modular split. investsite is
a top-level flat domain (not under cvm/), so this is the FIRST investsite
adapter (no pre-existing investsite_* adapters — investsite modes were
previously consumed directly via route() + JSON, not via the report tool's
adapter layer).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)


# ── KPI formatting ───────────────────────────────────────────────────────────
# Each investsite.dashboard() KPI carries a `unit` ("pct", "num", "int",
# "text", "brl") that tells us how to format the value. Map each unit to a
# format spec understood by tools.report_ops.formats.apply_fmt(). Falls back
# to "text" for unknown units so the KPI still renders (just without compact
# formatting).
_UNIT_TO_SPEC = {
    "pct":  "pct",    # ROE + Dividend Yield stored as fractions (0.15 = 15%)
    "num":  "num",    # P/L, P/VPA, EV/EBITDA raw multiples
    "int":  "int",
    "text": "text",
    "brl":  "brl",    # kept for symmetry, not currently used by investsite KPIs
}


def _format_kpi(k: dict) -> dict:
    """Convert an investsite.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "P/L", "value": "5,15", "unit": "num"}
            (value may already be pre-formatted by report.py -- if so, pass
            through unchanged when it's already a string.)
    Output: {"label": "P/L", "value": "5,15", "format": "num"}
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

@register_adapter("investsite_dashboard")
def investsite_dashboard(result: dict) -> dict:
    """Flatten investsite.dashboard() result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from investsite.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data
    correctly. KPI cards are re-formatted via the unit -> spec map.
    """
    if not _ok(result):
        return _error_table(result, title="Investsite Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Investsite Dashboard")

    # Format the top-level KPI cards (each KPI carries a `unit` -> format spec).
    kpis_in = result.get("kpis") or []
    kpis_out = [_format_kpi(k) for k in kpis_in]

    # [v2.0] Preserve group field on tabs + pass company_header + freshness_footer.
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
