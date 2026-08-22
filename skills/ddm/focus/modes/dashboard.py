"""Mode: dashboard -- DDM Focus (Boletim Focus) dashboard.

[v1] Multi-tab dashboard with subtabs:

  Tab 1: Focus (group: Boletim)
    - 4 subtabs (one per target year: 2026, 2027, 2028, 2029)
    - Each subtab: year table (all 13 indicators for that year)

  Tabs 2-13: Per indicator (group: Indicadores)
    - One tab per indicator: IPCA, PIB Total, Cambio, Selic, IGP-M,
      IPCA Adm, Conta corrente, Balanca comercial, Investimento direto
      no pais, Divida liquida setor pub, Resultado primario,
      Resultado nominal.
    - Each tab has 3 subtabs: "Ha 4 semanas" | "1 sem" | "Hoje"
    - Each subtab: indicator table (all 4 years for that time window)
    - Plus a chart at the top: grouped bar chart showing 3 time windows
      x 4 years for that indicator.

The dashboard pulls a single snapshot via all_data() (one query, latest
ref_date) and slices it into the per-year and per-indicator views in
memory. This is cheap (4 years x 13 indicators = 52 rows) so no
per-tab query is needed.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.focus._registry import register_mode
from skills.ddm.focus.report import (
    build_kpi_card, build_year_table, build_indicator_table,
    build_indicator_chart, build_error_section,
)
from skills.ddm.focus.helpers import format_value
from data_sources.ddm.focus.query_engine import all_data, summary


# 12 indicators (matching the page). The order is preserved for tab order.
_INDICATORS = [
    "IPCA", "PIB Total", "Câmbio", "Selic", "IGP-M", "IPCA Adm",
    "Conta corrente", "Balança comercial", "Investimento direto no país",
    "Dívida líquida setor pub", "Resultado primário", "Resultado nominal",
]

# 3 time-window subtabs for each indicator tab. Each subtab shows the
# table for that single window's column across all 4 years. The chart
# at the top of each indicator tab shows all 3 windows side-by-side.
_WINDOWS = [
    ("four_weeks_ago", "Ha 4 semanas"),
    ("one_week_ago",   "1 sem"),
    ("today",          "Hoje"),
]


def _safe_call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_year_subtab(obs_all: list[dict], year: int) -> dict:
    """Build one year subtab with a year table.

    Returns a subtab dict: {"name": "2026", "sections": [year_table]}.
    """
    year_obs = [o for o in obs_all if o.get("year") == year]
    if not year_obs:
        return {
            "name":     str(year),
            "sections": [build_error_section(
                f"Ano {year}",
                f"Sem dados para o ano {year}.")],
        }
    sections = [build_year_table(
        f"Indicadores - {year}",
        year_obs,
        year=year,
        description=(
            f"Boletim Focus para o ano {year}. Cada linha mostra um "
            f"indicador com os valores 'Ha 4 semanas', '1 sem' e 'Hoje', "
            f"alem da comparacao (Comp.) e do numero de respondentes "
            f"(Resp.). Clique no cabecalho das colunas para ordenar."
        ),
    )]
    return {"name": str(year), "sections": sections}


def _build_focus_tab(obs_all: list[dict], years: list[int]) -> dict:
    """Build the Focus tab with 4 subtabs (one per year)."""
    subtabs = [_build_year_subtab(obs_all, y) for y in years]
    return {
        "name":     "Focus",
        "group":    "Boletim",
        "sections": [{
            "type": "subtabs",
            "tabs": subtabs,
        }],
    }


def _build_indicator_tab(obs_all: list[dict], indicator: str) -> dict:
    """Build one indicator tab with chart + single table (no subtabs).

    [v2] Removed the 3 time-window subtabs — they showed the same table
    with all 3 windows. Now just chart + one table.
    """
    years_data = [o for o in obs_all if o.get("indicator") == indicator]
    if not years_data:
        return {
            "name":     indicator,
            "group":    "Indicadores",
            "sections": [build_error_section(
                indicator,
                f"Sem dados para o indicador '{indicator}'.")],
        }

    sections: list[dict] = []

    # Chart at the top: grouped bar (3 windows x 4 years).
    sections.append(build_indicator_chart(
        f"Evolução das expectativas — {indicator}",
        years_data,
        indicator=indicator,
        description=(
            f"Como as expectativas para {indicator} variam entre os anos "
            f"(2026, 2027, 2028, 2029) e entre as três janelas de tempo "
            f"(Há 4 semanas, 1 sem, Hoje). Cada grupo de barras representa "
            f"um ano; cada cor representa uma janela de tempo."
        ),
    ))

    # Single table: all 3 windows side by side, all 4 years.
    sections.append(build_indicator_table(
        f"{indicator} — por ano",
        years_data,
        indicator=indicator,
        description=(
            f"Valores para {indicator} em cada ano (2026-2029). "
            "Coluna 'Comp.' compara 'Hoje' com 'Há 4 semanas'. "
            "Valores negativos em vermelho. Clique no cabeçalho para ordenar."
        ),
    ))

    return {
        "name":     indicator,
        "group":    "Indicadores",
        "sections": sections,
    }


@register_mode(
    "dashboard",
    description=(
        "DDM Focus (Boletim Focus) dashboard. Multi-tab: 1 'Focus' tab "
        "with 4 year subtabs (2026-2029, each showing all 12 indicators) "
        "+ 12 per-indicator tabs (IPCA, PIB Total, Cambio, Selic, ...) "
        "each with a grouped bar chart + 3 time-window subtabs (Ha 4 "
        "semanas, 1 sem, Hoje). Data source: data_sources/ddm/focus/ "
        "(read-only queries against focus.db)."
    ),
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="focus", mode="dashboard")',
    ],
)
def dashboard() -> dict:
    _t0 = _dt.now()
    print(f"[ddm.focus] Starting dashboard...", flush=True)

    # Single snapshot query (one DB read for all 4 years x 12 indicators).
    snap = _safe_call(all_data)
    if snap.get("status") != "ok":
        return {
            "status": "ok",
            "mode":   "dashboard",
            "tabs":   [{
                "name":     "Focus",
                "group":    "Boletim",
                "sections": [build_error_section(
                    "Boletim Focus",
                    snap.get("error", "sem dados"))],
            }],
            "kpis":   [],
        }

    obs_all: list[dict] = snap.get("observations", [])
    ref_date = snap.get("ref_date", "")
    synced_at = snap.get("synced_at", "")

    # KPIs: latest sync date + total observations.
    kpis: list[dict] = []
    summ = _safe_call(summary)
    if summ.get("status") == "ok":
        kpis.append(build_kpi_card(
            "Data de referencia",
            ref_date,
            subtitle="Data do ultimo boletim Focus sincronizado",
            formatted=ref_date,
        ))
        kpis.append(build_kpi_card(
            "Anos cobertos",
            summ.get("year_count", 0),
            subtitle=", ".join(str(y) for y in summ.get("years", [])),
        ))
        kpis.append(build_kpi_card(
            "Indicadores",
            summ.get("indicator_count", 0),
            subtitle="Indicadores por ano",
        ))
        kpis.append(build_kpi_card(
            "Total de observacoes",
            summ.get("row_count", 0),
            subtitle=f"Ultima sincronizacao: {synced_at}",
        ))

    # Determine years from the data (default to 2026-2029 if empty).
    years = sorted(set(o.get("year") for o in obs_all if o.get("year")))
    if not years:
        years = [2026, 2027, 2028, 2029]

    tabs: list[dict] = []

    # Tab 1: Focus (group: Boletim) - 4 year subtabs.
    tabs.append(_build_focus_tab(obs_all, years))

    # Tabs 2-13: Per indicator (group: Indicadores).
    for indicator in _INDICATORS:
        tabs.append(_build_indicator_tab(obs_all, indicator))

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[ddm.focus] Done! {len(tabs)} tabs, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
    }
