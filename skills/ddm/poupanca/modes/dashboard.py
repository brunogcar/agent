"""Mode: dashboard -- 1-tab DDM poupanca dashboard with subtabs.

Tab:
  1. Poupanca  (group: Renda Fixa) - subtabs: Historico + Matriz
                                      (NO Comparativo tab - only 1 index)

The tab is composed as ONE section of type:"subtabs" containing 2 subtabs
(Historico + Matriz). The Historico subtab contains:
  - 3 KPI cards (latest month_value, acumulado_no_ano, acumulado_12m) -
    promoted to top level via _kpis
  - Historical chart with 3 datasets (month_value + acumulado_no_ano +
    acumulado_12m), last 60 months
  - History table (Mes/Ano | Rendimento | Acumulado no ano | Acumulado 12m),
    DESC order, right-aligned numeric columns, negative_red=True

The Matriz subtab contains the monthly matrix table (year x month, NO "Ano"
column - heatmap with red->white->green diverging colors for all 12 months).

When a sub-query fails (DB not synced, HTTP error), the dashboard still
returns status=ok with the failed tab containing an error section - mirrors
the CVM financials + bcb/macro + ddm/juros graceful-degradation contract.

Section titles DON'T repeat the index name (the index name is already in
the tab name) - e.g. "Evoluo mensal" (NOT "Poupanca - evolucao mensal").

Registered as "dashboard" in skills.ddm.poupanca._registry.MODES.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.poupanca._registry import register_mode
from skills.ddm.poupanca.report import (
    build_kpi_card, build_chart_section, build_table_section,
    build_matrix_table_section, build_error_section,
)
from data_sources.ddm.poupanca.query_engine import (
    poupanca_history, last_value, monthly_matrix,
)
from data_sources.ddm.poupanca.catalog import POUPANCA_CATALOG


# Single index slug.
_INDEX_SLUG = "poupanca"


def _safe_call(fn, **kwargs):
    """Call a query function and return its dict, or an error payload."""
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_historico_subtab(slug: str, name: str,
                             months: int) -> tuple[list[dict], list[dict]]:
    """Build the Historico subtab for the index.

    Returns (sections, kpis):
      sections - list of section dicts (chart + table, or error sections)
      kpis     - list of 3 KPI cards (empty on failure)

    Section titles DON'T repeat the index name (already in the tab name).
    """
    sections: list[dict] = []
    kpis: list[dict] = []

    # --- KPIs: latest month_value, acumulado_no_ano, acumulado_12m ---
    lv = _safe_call(last_value, slug=slug)
    if lv.get("status") == "ok":
        kpis = [
            build_kpi_card(
                f"{name} (mes)",
                lv.get("month_value"),
                subtitle=f"ref: {lv.get('ref_date', '')}",
            ),
            build_kpi_card(
                f"{name} (acumulado ano)",
                lv.get("acumulado_no_ano"),
                subtitle="acumulado no ano",
            ),
            build_kpi_card(
                f"{name} (acumulado 12m)",
                lv.get("acumulado_12m"),
                subtitle="acumulado 12 meses",
            ),
        ]
    else:
        sections.append(build_error_section(
            "Ultimo valor", lv.get("error", "sem dados")))

    # --- Historical chart + table (last N months) ---
    hist = _safe_call(poupanca_history, slug=slug, limit=months)
    if hist.get("status") == "ok":
        observations = hist.get("observations", [])
        sections.append(build_chart_section(
            "Evolucao mensal",
            observations,
            slug=slug,
            description=(f"Rendimento (%), acumulado no ano (%) e "
                         f"acumulado 12 meses (%) para {name}. "
                         f"Ultimos {months} meses. Acumulados usam SOMA "
                         f"(rendimento mensal e uma taxa percentual - "
                         f"somar produz o retorno cumulativo)."),
        ))
        sections.append(build_table_section(
            "Historico mensal",
            observations,
            limit=months,
            descending=True,
            description=("Dados derivados da matriz mensal (DESC). "
                         "Valores negativos em vermelho."),
        ))
    else:
        sections.append(build_error_section(
            "Historico", hist.get("error", "sem dados")))

    return sections, kpis


def _build_matriz_subtab(slug: str) -> list[dict]:
    """Build the Matriz subtab (monthly matrix heatmap).

    Section title doesn't repeat the index name.
    """
    sections: list[dict] = []
    mat = _safe_call(monthly_matrix, slug=slug)
    if mat.get("status") == "ok":
        sections.append(build_matrix_table_section(
            "Matriz mensal",
            mat,
            description=("Matriz ano x mes. Cores divergentes vermelho "
                         "-> branco -> verde indicam o valor relativo do "
                         "rendimento mensal (NAO ha coluna 'Ano' - poupanca "
                         "e rendimento mensal, nao acumulado)."),
        ))
    else:
        sections.append(build_error_section(
            "Matriz", mat.get("error", "sem dados")))
    return sections


def _build_index_tab(slug: str, months: int = 60) -> dict:
    """Build the index tab with subtabs (Historico + Matriz).

    Returns a tab dict: {"name": "Poupanca", "group": "Renda Fixa",
                         "sections": [<subtabs section>], "_kpis": [...]}.

    The "sections" list contains exactly ONE entry: a section of
    type:"subtabs" with 2 subtabs. KPIs are returned separately via the
    _kpis field so the dashboard can promote them to the top-level kpis list.
    """
    meta = POUPANCA_CATALOG.get(slug, ("Poupanca", "Renda Fixa", "", "%"))
    name = meta[0]
    category = meta[1]

    hist_sections, kpis = _build_historico_subtab(slug, name, months=months)
    matriz_sections = _build_matriz_subtab(slug)

    subtabs_section = {
        "type": "subtabs",
        "tabs": [
            {"name": "Historico", "sections": hist_sections},
            {"name": "Matriz",    "sections": matriz_sections},
        ],
    }

    return {
        "name":     name,
        "group":    category,
        "sections": [subtabs_section],
        "_kpis":    kpis,
    }


@register_mode(
    "dashboard",
    description=(
        "DDM poupanca dashboard - 1 tab: Poupanca. The tab uses subtabs "
        "(Historico + Matriz). Historico subtab shows KPIs (month_value, "
        "acumulado_no_ano, acumulado_12m) + 3-dataset line chart (monthly "
        "yield %, year-to-date SUM %, rolling 12m SUM %) + history table "
        "(negative_red=True). Matriz subtab shows a monthly matrix heatmap "
        "(red->white->green diverging for all 12 months - NO Ano column). "
        "NO Comparativo tab (only 1 index). KPIs at top level."
    ),
    params={
        "months": "int. Monthly-series window for the index tab. Default: 60.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="poupanca", mode="dashboard")',
    ],
)
def dashboard(months: int = 60) -> dict:
    """Build the 1-tab DDM poupanca dashboard.

    KPIs are collected per-tab and promoted to the top-level `kpis` array
    (mirrors the bcb/macro + ddm/inflation + ddm/juros v3+ dashboard contract).
    """
    _t0 = _dt.now()
    print(f"[ddm.poupanca] Starting dashboard...", flush=True)

    tabs: list[dict] = []
    kpis: list[dict] = []

    tab = _build_index_tab(_INDEX_SLUG, months=months)
    tabs.append(tab)
    kpis.extend(tab.pop("_kpis", []))

    errors = []
    for t in tabs:
        for s in t.get("sections", []):
            if s.get("type") == "subtabs":
                # Walk into subtabs to surface errors at top level.
                for sub in s.get("tabs", []):
                    for ss in sub.get("sections", []):
                        if ss.get("type") == "text" and \
                           "Erro ao consultar" in ss.get("body", ""):
                            errors.append(f"{t['name']}/{sub['name']}: "
                                          f"{ss['body']}")
            elif s.get("type") == "text" and \
                    "Erro ao consultar" in s.get("body", ""):
                errors.append(f"{t['name']}: {s['body']}")

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[ddm.poupanca] Done! {len(tabs)} tabs, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
        "errors": errors,
    }
