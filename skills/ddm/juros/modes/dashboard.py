"""Mode: dashboard -- 4-tab DDM juros dashboard with subtabs.

Tabs:
  1. Selic       (group: Indices) - subtabs: Historico + Matriz
  2. Meta Selic  (group: Indices) - same
  3. CDI         (group: Indices) - same
  4. Comparativo (group: Analise) - overlay chart (month_value, last 24m)

Each per-index tab is composed as ONE section of type:"subtabs" containing
2 subtabs (Histórico + Matriz). The Histórico subtab contains:
  - 3 KPI cards (latest month_value, media_no_ano, media_12m) - promoted to
    top level via _kpis
  - Historical chart with 3 datasets (month_value + media_no_ano + media_12m),
    last 60 months
  - History table (Mes/Ano | Indice do mes | Media no ano | Media 12 meses),
    DESC order, right-aligned numeric columns

The Matriz subtab contains the monthly matrix table (year x month, NO "Ano"
column - heatmap with red->white->green diverging colors for all 12 months).

The Comparativo tab overlays the month_value series of all 3 indices over
the last 24 months. It has NO tables (chart-only).

When a sub-query fails (DB not synced, HTTP error), the dashboard still
returns status=ok with the failed tab containing an error section - mirrors
the CVM financials + bcb/macro + ddm/inflation graceful-degradation contract.

Registered as "dashboard" in skills.ddm.juros._registry.MODES.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.juros._registry import register_mode
from skills.ddm.juros.report import (
    build_kpi_card, build_chart_section, build_table_section,
    build_matrix_table_section, build_overlay_chart_section,
    build_error_section,
)
from skills.ddm.juros.helpers import format_pct
from data_sources.ddm.juros.query_engine import (
    juros_history, last_value, monthly_matrix,
)
from data_sources.ddm.juros.catalog import JUROS_CATALOG


# Slugs + display order for the per-index tabs.
_INDEX_SLUGS = ["selic", "meta-selic", "cdi"]


def _safe_call(fn, **kwargs):
    """Call a query function and return its dict, or an error payload."""
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_historico_subtab(slug: str, name: str,
                             months: int) -> tuple[list[dict], list[dict]]:
    """Build the Historico subtab for one index.

    Returns (sections, kpis):
      sections - list of section dicts (chart + table, or error sections)
      kpis     - list of 3 KPI cards (empty on failure)
    """
    sections: list[dict] = []
    kpis: list[dict] = []

    # --- KPIs: latest month_value, media_no_ano, media_12m ---
    lv = _safe_call(last_value, slug=slug)
    if lv.get("status") == "ok":
        kpis = [
            build_kpi_card(
                f"{name} (mes)",
                lv.get("month_value"),
                subtitle=f"ref: {lv.get('ref_date', '')}",
                format_fn=format_pct,
            ),
            build_kpi_card(
                f"{name} (media ano)",
                lv.get("media_no_ano"),
                subtitle="media no ano",
                format_fn=format_pct,
            ),
            build_kpi_card(
                f"{name} (media 12m)",
                lv.get("media_12m"),
                subtitle="media 12 meses",
                format_fn=format_pct,
            ),
        ]
    else:
        sections.append(build_error_section(
            "Último valor", lv.get("error", "sem dados")))

    # --- Historical chart + table (last N months) ---
    hist = _safe_call(juros_history, slug=slug, limit=months)
    if hist.get("status") == "ok":
        observations = hist.get("observations", [])
        sections.append(build_chart_section(
            "Evolução mensal",
            observations,
            slug=slug,
            description=(f"Indice do mes (% a.a.), media no ano (%) e "
                         f"media 12 meses (%) para {name}. "
                         f"Ultimos {months} meses."),
        ))
        sections.append(build_table_section(
            "Histórico mensal",
            observations,
            limit=months,
            descending=True,
            description="Dados derivados da matriz mensal (DESC).",
        ))
    else:
        sections.append(build_error_section(
            "Histórico", hist.get("error", "sem dados")))

    return sections, kpis


def _build_matriz_subtab(slug: str, name: str) -> list[dict]:
    """Build the Matriz subtab for one index (monthly matrix heatmap)."""
    sections: list[dict] = []
    mat = _safe_call(monthly_matrix, slug=slug)
    if mat.get("status") == "ok":
        sections.append(build_matrix_table_section(
            "Matriz mensal",
            mat,
            description=("Matriz ano x mes. Cores divergentes vermelho "
                         "-> branco -> verde indicam o valor relativo da "
                         "taxa mensal (NAO ha coluna 'Ano' - juros sao "
                         "taxas diarias, nao acumulado)."),
        ))
    else:
        sections.append(build_error_section(
            "Matriz", mat.get("error", "sem dados")))
    return sections


def _build_index_tab(slug: str, months: int = 0) -> dict:
    """Build one per-index tab with subtabs (Historico + Matriz).

    Returns a tab dict: {"name": "Selic", "group": "Indices",
                         "sections": [<subtabs section>], "_kpis": [...]}.

    The "sections" list contains exactly ONE entry: a section of
    type:"subtabs" with 2 subtabs. KPIs are returned separately via the
    _kpis field so the dashboard can promote them to the top-level kpis list.
    """
    meta = JUROS_CATALOG.get(slug, (slug.upper(), "Juros", "", "% a.a."))
    name = meta[0]

    hist_sections, kpis = _build_historico_subtab(slug, name, months=months)
    matriz_sections = _build_matriz_subtab(slug, name)

    subtabs_section = {
        "type": "subtabs",
        "tabs": [
            {"name": "Historico", "sections": hist_sections},
            {"name": "Matriz",    "sections": matriz_sections},
        ],
    }

    return {
        "name":     name,
        "group":    "Indices",
        "sections": [subtabs_section],
        "_kpis":    kpis,
    }


def _build_comparativo_tab(months: int = 0) -> dict:
    """Build the Comparativo tab (overlay chart, NO tables).

    Returns a tab dict: {"name": "Comparativo", "group": "Analise",
                         "sections": [<chart>]}.
    """
    series = []
    for slug in _INDEX_SLUGS:
        meta = JUROS_CATALOG.get(slug, (slug.upper(), "Juros", "", "% a.a."))
        hist = _safe_call(juros_history, slug=slug, limit=months)
        if hist.get("status") == "ok":
            observations = hist.get("observations", [])
            series.append({
                "slug":         slug,
                "name":         meta[0],
                "observations": observations,
            })

    if not series:
        return {
            "name":     "Comparativo",
            "group":    "Analise",
            "sections": [build_error_section(
                "Comparativo", "Nenhum indice sincronizado.")],
            "_kpis":    [],
        }

    sections = [build_overlay_chart_section(
        f"Comparativo - indice do mes (ultimos {months} meses)",
        series,
        description=("Sobreposicao do indice do mes (% a.a.) para Selic, "
                     "Meta Selic e CDI. Permite comparar a trajetoria "
                     "das taxas de juros brasileiras entre os 3 indices."),
    )]

    return {
        "name":     "Comparativo",
        "group":    "Analise",
        "sections": sections,
        "_kpis":    [],
    }


@register_mode(
    "dashboard",
    description=(
        "DDM juros dashboard - 4 tabs: Selic, Meta Selic, CDI, Comparativo. "
        "Each index tab uses subtabs (Historico + Matriz). Historico subtab "
        "shows KPIs (month_value, media_no_ano, media_12m) + 3-dataset line "
        "chart (daily rate %, year-to-date average %, rolling 12m average %) "
        "+ history table. Matriz subtab shows a monthly matrix heatmap "
        "(red->white->green diverging for all 12 months - NO Ano column). "
        "Comparativo tab overlays month_value for all 3 indices "
        "(last 24 months). KPIs at top level."
    ),
    params={
        "months": "int. Monthly-series window for per-index tabs. Default: 0 (all available data).",
        "compare_months": "int. Window for Comparativo tab. Default: 0 (all available data).",
    },
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="juros", mode="dashboard")',
    ],
)
def dashboard(months: int = 0, compare_months: int = 0) -> dict:
    """Build the 4-tab DDM juros dashboard.

    KPIs are collected per-tab and promoted to the top-level `kpis` array
    (mirrors the bcb/macro + ddm/inflation v3 dashboard contract).
    """
    _t0 = _dt.now()
    print(f"[ddm.juros] Starting dashboard...", flush=True)

    tabs: list[dict] = []
    kpis: list[dict] = []

    for slug in _INDEX_SLUGS:
        tab = _build_index_tab(slug, months=months)
        tabs.append(tab)
        kpis.extend(tab.pop("_kpis", []))

    cmp_tab = _build_comparativo_tab(months=compare_months)
    cmp_tab.pop("_kpis", None)
    tabs.append(cmp_tab)

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
    print(f"[ddm.juros] Done! {len(tabs)} tabs, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
        "errors": errors,
    }
