"""Mode: dashboard -- B3 index composition dashboard.

Multi-tab dashboard:
  Resumo    -- summary of all synced indices
  IBOV      -- Ibovespa composition (chart + table)
  SMLL      -- Small Cap composition
  BDRX      -- BDR composition
  IFIX      -- FII composition
  IDIV      -- Dividend composition
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.b3.index._registry import register_mode
from skills.b3.index.report import build_kpi_card, build_index_tab
from skills.b3.index.helpers import build_constituent_table

from data_sources.b3.index.catalog import ACTIVE_INDICES
from data_sources.b3.index.query_engine import index as query_index, summary


@register_mode(
    "dashboard",
    description="B3 index dashboard - 6 tabs: Resumo + 5 indices (IBOV/SMLL/BDRX/IFIX/IDIV)",
    params={},
    include_in_all=False,
    examples=['skill(domain="b3", sub_domain="index", mode="dashboard")'],
)
def dashboard(**kwargs) -> dict:
    """Build the B3 index dashboard."""
    _t0 = _dt.now()
    print("[b3.index] Starting dashboard...", flush=True)

    summary_data = summary()
    if summary_data.get("status") != "ok":
        return summary_data

    # [v5] One-line section timers (ratios pattern): 1 (Resumo) + N indices.
    _n_indices = len(ACTIVE_INDICES)
    _SEC_TOTAL = 1 + _n_indices
    _sec_count = 0
    _sec_t0 = _dt.now()

    # Build KPI cards (one per active index)
    kpis = []
    for idx in summary_data.get("indices", []):
        if idx["active"] and idx["constituent_count"] > 0:
            kpis.append(build_kpi_card(
                idx["code"],
                idx["constituent_count"],
                "constituintes",
                subtitle=f"ref: {idx['last_date']}",
            ))

    # Build tabs
    tabs = []

    # ── Section 1/(1+N): Resumo ───────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    overview_rows = []
    for idx in summary_data.get("indices", []):
        if idx["active"]:
            overview_rows.append([
                idx["code"], idx["name"], str(idx["constituent_count"]),
                idx["last_date"] or "-",
            ])

    tabs.append({
        "name": "Resumo",
        "group": "Resumo",
        "sections": [{
            "type": "table",
            "title": "Indices Sincronizados",
            "columns": ["Codigo", "Nome", "Constituintes", "Data Ref."],
            "rows": overview_rows,
        }],
    })
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Resumo ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Sections 2..N: One tab per active index ───────────────────
    for code in ACTIVE_INDICES:
        _sec_count += 1
        _s_t0 = _dt.now()
        idx_data = query_index(code)
        tabs.append(build_index_tab(code, idx_data))
        _s_elapsed = (_dt.now() - _s_t0).total_seconds()
        _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
        print(f"  [sections] {_sec_count}/{_SEC_TOTAL} {code} ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[b3.index] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "title": "Dashboard de Indices - B3",
        "tabs": tabs,
        "kpis": kpis,
    }
