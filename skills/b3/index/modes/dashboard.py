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
    print("[b3.index] Building dashboard...", flush=True)

    summary_data = summary()
    if summary_data.get("status") != "ok":
        return summary_data

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

    # Resumo tab
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

    # One tab per active index
    for code in ACTIVE_INDICES:
        idx_data = query_index(code)
        tabs.append(build_index_tab(code, idx_data))

    print(f"[b3.index] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)

    return {
        "status": "ok",
        "title": "Dashboard de Indices - B3",
        "tabs": tabs,
        "kpis": kpis,
    }
