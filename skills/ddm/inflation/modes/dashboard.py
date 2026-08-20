"""Mode: dashboard -- DDM inflation dashboard.

[v3] Restructured to 4 tabs with subtabs:
  1. IGP-M       (group: Indices) - subtabs: Histórico + Matriz
  2. IPCA        (group: Indices) - subtabs: Histórico + Matriz
  3. INPC        (group: Indices) - subtabs: Histórico + Matriz
  4. Comparativo (group: Análise) - overlay chart (12m acumulado, last 24m)

Each index tab has a `type: "subtabs"` section with 2 subtabs:
  - "Histórico": evolução chart + historico table (DESC, newest first)
  - "Matriz": monthly matrix heatmap (red→white→green for months, white→blue for Ano)

Section titles don't repeat the index name (already in tab name).
Date display: "Jul/2026" format (not ISO "2026-07").
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.inflation._registry import register_mode
from skills.ddm.inflation.report import (
    build_kpi_card, build_chart_section, build_table_section,
    build_matrix_table_section, build_overlay_chart_section,
    build_error_section,
)
from data_sources.ddm.inflation.query_engine import (
    index_history, last_value, monthly_matrix,
)
from data_sources.ddm.inflation.catalog import INDEX_CATALOG


_INDEX_SLUGS = ["igp-m", "ipca", "inpc"]


def _safe_call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_index_tab(slug: str, months: int = 0) -> dict:
    """Build one index tab with subtabs (Histórico + Matriz).

    Returns a tab dict: {"name": "IGP-M", "group": "Indices",
                         "sections": [<subtabs section>]}.

    The subtabs section has type="subtabs" with 2 subtab entries:
      - {"name": "Histórico", "sections": [chart, table]}
      - {"name": "Matriz", "sections": [heatmap]}
    """
    meta = INDEX_CATALOG.get(slug, (slug.upper(), "Inflacao", "", "%"))
    name = meta[0]
    kpis: list[dict] = []

    # KPIs (collected for top-level)
    lv = _safe_call(last_value, slug=slug)
    if lv.get("status") == "ok":
        kpis = [
            build_kpi_card(f"{name} (mes)", lv.get("month_value"),
                           subtitle=f"ref: {lv.get('ref_date', '')}"),
            build_kpi_card(f"{name} (ano)", lv.get("year_acumulado"),
                           subtitle="acumulado no ano"),
            build_kpi_card(f"{name} (12m)", lv.get("acumulado_12m"),
                           subtitle="acumulado 12 meses"),
        ]

    # Subtab 1: Histórico (chart + table)
    historico_sections: list[dict] = []
    hist = _safe_call(index_history, slug=slug, limit=months)
    if hist.get("status") == "ok":
        observations = hist.get("observations", [])
        historico_sections.append(build_chart_section(
            "Evolução mensal",
            observations,
            slug=slug,
            description=(f"Variação mensal (%) e acumulado 12 meses (%) "
                         f"para {name}. Últimos {months} meses."),
        ))
        historico_sections.append(build_table_section(
            "Histórico mensal",
            observations,
            limit=months,
            description="Dados brutos (mais recente primeiro).",
        ))
    else:
        historico_sections.append(build_error_section(
            "Histórico", hist.get("error", "sem dados")))

    # Subtab 2: Matriz (heatmap)
    matriz_sections: list[dict] = []
    mat = _safe_call(monthly_matrix, slug=slug)
    if mat.get("status") == "ok":
        matriz_sections.append(build_matrix_table_section(
            "Matriz mensal",
            mat,
            description=("Matriz ano × mês. Coluna final 'Ano' é o acumulado no ano. "
                         "Cores: vermelho=negativo, branco=zero, verde=positivo "
                         "(mensal); branco→azul (anual)."),
        ))
    else:
        matriz_sections.append(build_error_section(
            "Matriz", mat.get("error", "sem dados")))

    # Build the subtabs section
    subtabs_section = {
        "type": "subtabs",
        "tabs": [
            {"name": "Histórico", "sections": historico_sections},
            {"name": "Matriz", "sections": matriz_sections},
        ],
    }

    return {
        "name":     name,
        "group":    "Indices",
        "sections": [subtabs_section],
        "_kpis":    kpis,
    }


def _build_comparativo_tab(months: int = 0) -> dict:
    series = []
    for slug in _INDEX_SLUGS:
        meta = INDEX_CATALOG.get(slug, (slug.upper(), "Inflacao", "", "%"))
        hist = _safe_call(index_history, slug=slug, limit=months)
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
            "group":    "Análise",
            "sections": [build_error_section("Comparativo", "Nenhum índice sincronizado.")],
            "_kpis":    [],
        }

    sections = [build_overlay_chart_section(
        f"Acumulado 12m (últimos {months} meses)",
        series,
        description=("Sobreposição do acumulado 12 meses (%) para IGP-M, "
                     "IPCA e INPC. Permite comparar a trajetória da "
                     "inflação entre os 3 índices."),
    )]

    return {
        "name":     "Comparativo",
        "group":    "Análise",
        "sections": sections,
        "_kpis":    [],
    }


@register_mode(
    "dashboard",
    description=(
        "DDM inflation dashboard. 4 tabs: IGP-M, IPCA, INPC (each with "
        "Histórico + Matriz subtabs), Comparativo (overlay chart). "
        "Each index has subtabs: Histórico (chart + table) + Matriz (heatmap). "
        "Comparativo overlays 12m acumulado for all 3 indices."
    ),
    params={
        "months": "int. Monthly-series window for per-index tabs. Default: 0 (all available data).",
        "compare_months": "int. Window for Comparativo tab. Default: 0 (all available data).",
    },
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="inflation", mode="dashboard")',
    ],
)
def dashboard(months: int = 0, compare_months: int = 0) -> dict:
    _t0 = _dt.now()
    print(f"[ddm.inflation] Starting dashboard...", flush=True)

    tabs: list[dict] = []
    kpis: list[dict] = []

    for slug in _INDEX_SLUGS:
        tab = _build_index_tab(slug, months=months)
        tabs.append(tab)
        kpis.extend(tab.pop("_kpis", []))

    cmp_tab = _build_comparativo_tab(months=compare_months)
    cmp_tab.pop("_kpis", None)
    tabs.append(cmp_tab)

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[ddm.inflation] Done! {len(tabs)} tabs, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
    }
