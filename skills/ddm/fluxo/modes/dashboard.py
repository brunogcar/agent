"""Mode: dashboard -- DDM Fluxo (B3 investment flow) dashboard.

[v1] 5-tab dashboard:

  Tab 1: Fluxo (group: Fluxo)
    - KPIs (top-level): latest date, total estrangeiro (sum), total
      institucional, total pessoa_fisica.
    - Bar chart with 4 datasets (Estrangeiro, Institucional,
      Pessoa fisica, Inst. Financeira), daily granularity, range selector.
    - Sortable table: all columns, all dates.

  Tabs 2-5: Per investor (group: Investidores)
    - Tab 2: Estrangeiro (blue)
    - Tab 3: Institucional (red)
    - Tab 4: Pessoa fisica (amber)
    - Tab 5: Inst. Financeira (green)
    Each has 3 subtabs:
      - Diario: bar chart (green/red per day) + table (daily flow)
      - Mensal: line chart (monthly cumulative) + table
      - Anual:  line chart (running annual cumulative) + table

The dashboard pulls the daily series via fluxo_data() (one query, all
dates ASC), then slices / aggregates in-memory into per-investor views.
For monthly + annual views, the dashboard calls the query_engine helpers
(monthly_cumulative, annual_cumulative) which do the GROUP BY + SUM in
SQLite (efficient for ~247 rows but scales to thousands).
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.fluxo._registry import register_mode
from skills.ddm.fluxo.report import (
    build_kpi_card, build_fluxo_table, build_fluxo_chart,
    build_investor_daily_chart, build_investor_monthly_chart,
    build_investor_annual_chart, build_investor_table,
    build_error_section,
)
from skills.ddm.fluxo.helpers import format_brl, format_date, format_brl_from_millions, format_int
from data_sources.ddm.fluxo.query_engine import (
    fluxo_data, fluxo_by_investor, summary, monthly_cumulative,
    annual_cumulative,
)


# 4 investors (matching the per-investor tabs). The order is preserved
# for tab order. "outros" is intentionally NOT a per-investor tab - it's
# a residual category and is only shown in the Fluxo table.
_INVESTORS = [
    ("estrangeiro",     "Estrangeiro"),
    ("institucional",   "Institucional"),
    ("pessoa_fisica",   "Pessoa fisica"),
    ("inst_financeira", "Inst. Financeira"),
]

# 3 subtabs for each investor tab.
_SUBTABS = [
    ("daily", "Diario"),
    ("monthly", "Mensal"),
    ("annual", "Anual"),
]


def _safe_call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_fluxo_tab(obs_all: list[dict]) -> dict:
    """Build the Fluxo tab with chart + sortable table.

    The chart shows daily flow for 4 investors (Estrangeiro, Institucional,
    Pessoa fisica, Inst. Financeira) as 4 colored bar datasets. The table
    shows all daily observations, sorted DESC by date (newest first).
    """
    sections: list[dict] = []

    if not obs_all:
        sections.append(build_error_section(
            "Fluxo de investimento",
            "Sem dados de fluxo. Execute sync_all primeiro."))
        return {
            "name":     "Fluxo",
            "group":    "Fluxo",
            "sections": sections,
        }

    # Daily chart with 4 investor datasets.
    sections.append(build_fluxo_chart(
        "Fluxo diario por investidor",
        obs_all,
        description=(
            "Fluxo diario de investimento na B3 por tipo de investidor "
            "(em milhoes de R$). Estrangeiro (azul), Institucional "
            "(vermelho), Pessoa fisica (amarelo), Inst. Financeira "
            "(verde). Valores negativos indicam saida (venda); "
            "positivos indicam entrada (compra)."
        ),
    ))

    # Sortable table with all columns + all dates.
    sections.append(build_fluxo_table(
        "Tabela diaria completa",
        obs_all,
        description=(
            "Todas as observacoes diarias. Clique no cabecalho das "
            "colunas para ordenar (crescente/decrescente). A coluna "
            "'Data' ordena cronologicamente; as colunas de valor "
            "ordenam numericamente. Valores negativos em vermelho."
        ),
    ))

    return {
        "name":     "Fluxo",
        "group":    "Fluxo",
        "sections": sections,
    }


def _build_investor_subtab_daily(obs_all: list[dict],
                                 investor: str, label: str) -> dict:
    """Diario subtab: bar chart + daily table for ONE investor."""
    # Extract date + value for this investor.
    daily_obs = [
        {"ref_date": o["ref_date"], "value": o.get(investor)}
        for o in obs_all
        if o.get("ref_date")
    ]
    sections: list[dict] = []
    sections.append(build_investor_daily_chart(
        f"Fluxo diario - {label}",
        investor,
        daily_obs,
        description=(
            f"Fluxo diario de {label} na B3 (em milhoes de R$). Barras "
            f"verdes indicam entrada (compra); vermelhas indicam saida "
            f"(venda)."
        ),
    ))
    sections.append(build_investor_table(
        f"Tabela diaria - {label}",
        daily_obs,
        investor=investor,
        description=(
            f"Valores diarios de {label}. Clique no cabecalho para "
            f"ordenar. Valores negativos em vermelho."
        ),
    ))
    return {"name": "Diario", "sections": sections}


def _build_investor_subtab_monthly(investor: str, label: str) -> dict:
    """Mensal subtab: monthly cumulative line chart + table."""
    monthly_resp = _safe_call(monthly_cumulative, investor=investor)
    if monthly_resp.get("status") != "ok":
        return {
            "name":     "Mensal",
            "sections": [build_error_section(
                f"Mensal - {label}",
                monthly_resp.get("error", "sem dados"))],
        }
    monthly_data = monthly_resp.get("observations", [])

    # Build a table from the monthly data.
    # [v2] Pass both ref_date (for sorting: "2026-08") and date_label
    # (for display: "Ago/2026"). build_investor_table uses date_label
    # if present, otherwise formats ref_date as DD/MM/YYYY.
    table_obs = [
        {
            "ref_date": d.get("month", ""),
            "date_label": d.get("label", ""),
            "value": d.get("value"),
        }
        for d in monthly_data
    ]

    sections: list[dict] = []
    sections.append(build_investor_monthly_chart(
        f"Acumulado mensal - {label}",
        monthly_data,
        description=(
            f"Soma mensal do fluxo diario de {label} (em milhoes de "
            f"R$). Cada ponto representa o total acumulado no mes. "
            f"Meses positivos em verde; negativos em vermelho."
        ),
    ))
    sections.append(build_investor_table(
        f"Tabela mensal - {label}",
        table_obs,
        investor=investor,
        description=(
            f"Valores mensais acumulados de {label}. Clique no cabecalho "
            f"para ordenar."
        ),
    ))
    return {"name": "Mensal", "sections": sections}


def _build_investor_subtab_annual(investor: str, label: str) -> dict:
    """Anual subtab: running cumulative line chart + table."""
    annual_resp = _safe_call(annual_cumulative, investor=investor)
    if annual_resp.get("status") != "ok":
        return {
            "name":     "Anual",
            "sections": [build_error_section(
                f"Anual - {label}",
                annual_resp.get("error", "sem dados"))],
        }
    cum_data = annual_resp.get("observations", [])

    sections: list[dict] = []
    sections.append(build_investor_annual_chart(
        f"Acumulado anual - {label}",
        cum_data,
        description=(
            f"Soma acumulada do fluxo diario de {label} (em milhoes de "
            f"R$). Cada ponto representa o total acumulado desde o "
            f"primeiro dia disponivel ate aquela data. Util para ver "
            f"o saldo liquido YTD (year-to-date)."
        ),
    ))
    sections.append(build_investor_table(
        f"Tabela acumulada - {label}",
        cum_data,
        investor=investor,
        description=(
            f"Valores acumulados (running sum) de {label}. Clique no "
            f"cabecalho para ordenar."
        ),
    ))
    return {"name": "Anual", "sections": sections}


def _build_investor_tab(obs_all: list[dict], investor: str,
                        label: str) -> dict:
    """Build one investor tab with 3 subtabs (Diario/Mensal/Anual)."""
    if not obs_all:
        return {
            "name":     label,
            "group":    "Investidores",
            "sections": [build_error_section(
                label,
                f"Sem dados para o investidor '{label}'.")],
        }

    subtabs = [
        _build_investor_subtab_daily(obs_all, investor, label),
        _build_investor_subtab_monthly(investor, label),
        _build_investor_subtab_annual(investor, label),
    ]
    return {
        "name":     label,
        "group":    "Investidores",
        "sections": [{"type": "subtabs", "tabs": subtabs}],
    }


@register_mode(
    "dashboard",
    description=(
        "DDM Fluxo (B3 investment flow) dashboard. Multi-tab: 1 'Fluxo' "
        "tab (group: Fluxo) with 4-dataset daily bar chart + sortable "
        "table of all daily observations + 4 per-investor tabs (group: "
        "Investidores: Estrangeiro, Institucional, Pessoa fisica, Inst. "
        "Financeira) each with 3 subtabs (Diario/Mensal/Anual) showing "
        "a daily bar chart, a monthly cumulative line chart, and a "
        "running annual cumulative line chart. Data source: "
        "data_sources/ddm/fluxo/ (read-only queries against fluxo.db)."
    ),
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="fluxo", mode="dashboard")',
    ],
)
def dashboard() -> dict:
    _t0 = _dt.now()
    print(f"[ddm.fluxo] Starting dashboard...", flush=True)

    # Single query: all daily observations (ASC).
    snap = _safe_call(fluxo_data)
    if snap.get("status") != "ok":
        return {
            "status": "ok",
            "mode":   "dashboard",
            "tabs":   [{
                "name":     "Fluxo",
                "group":    "Fluxo",
                "sections": [build_error_section(
                    "Fluxo de investimento",
                    snap.get("error", "sem dados"))],
            }],
            "kpis":   [],
        }

    obs_all: list[dict] = snap.get("observations", [])

    # [v2] KPIs: 2 rows of 5 boxes each (10 total).
    #
    # Row 1 (YTD — since Jan 1 of the latest year):
    #   1. Ultima data (latest sync date, DD/MM/YYYY)
    #   2-5. Liquido anual {investor} (YTD net per investor, auto-scale bi/mi)
    #
    # Row 2 (Rolling 365 days):
    #   1. Dias na base (total day count in DB)
    #   2-5. Liquido 365d {investor} (last 365 days net per investor, auto-scale)
    kpis: list[dict] = []
    summ = _safe_call(summary)
    last_date = ""
    row_count = 0
    if summ.get("status") == "ok":
        last_date = summ.get("last_date", "")
        row_count = summ.get("row_count", 0) or summ.get("sync_rows", 0)
    elif obs_all:
        last_date = max(o["ref_date"] for o in obs_all if o.get("ref_date"))
        row_count = len(obs_all)

    # ── Row 1: YTD (year-to-date) ───────────────────────────────────────
    kpis.append(build_kpi_card(
        "Ultima data",
        last_date,
        subtitle="Dia de negociacao mais recente sincronizado",
        formatted=format_date(last_date) if last_date else "-",
    ))

    # Determine the current year from last_date (or today's date as fallback).
    current_year = (last_date[:4] if last_date else _dt.now().strftime("%Y"))

    # Per-investor YTD net (sum of daily values where ref_date starts with current_year).
    for field, label in _INVESTORS:
        ytd_total = 0.0
        any_value = False
        for o in obs_all:
            ref = o.get("ref_date", "")
            v = o.get(field)
            if ref.startswith(current_year) and v is not None:
                ytd_total += v
                any_value = True
        if any_value:
            kpis.append(build_kpi_card(
                f"Liquido anual {label}",
                ytd_total,
                subtitle=f"YTD {current_year} (milhoes R$)",
                formatted=format_brl_from_millions(ytd_total),
            ))
        else:
            kpis.append(build_kpi_card(
                f"Liquido anual {label}",
                0.0,
                subtitle=f"YTD {current_year} (sem dados)",
                formatted="-",
            ))

    # ── Row 2: Rolling 365 days ─────────────────────────────────────────
    kpis.append(build_kpi_card(
        "Dias na base",
        row_count,
        subtitle="Total de dias sincronizados no banco",
        formatted=format_int(row_count) if row_count else "-",
    ))

    # Per-investor last-365-days net.
    # Compute the cutoff date (365 days before last_date).
    from datetime import timedelta as _td
    try:
        last_dt = _dt.strptime(last_date, "%Y-%m-%d") if last_date else _dt.now()
    except ValueError:
        last_dt = _dt.now()
    cutoff_date = (last_dt - _td(days=365)).strftime("%Y-%m-%d")

    for field, label in _INVESTORS:
        rolling_total = 0.0
        any_value = False
        for o in obs_all:
            ref = o.get("ref_date", "")
            v = o.get(field)
            if ref >= cutoff_date and v is not None:
                rolling_total += v
                any_value = True
        if any_value:
            kpis.append(build_kpi_card(
                f"Liquido 365d {label}",
                rolling_total,
                subtitle=f"Ultimos 365 dias (milhoes R$)",
                formatted=format_brl_from_millions(rolling_total),
            ))
        else:
            kpis.append(build_kpi_card(
                f"Liquido 365d {label}",
                0.0,
                subtitle="Ultimos 365 dias (sem dados)",
                formatted="-",
            ))

    tabs: list[dict] = []

    # Tab 1: Fluxo (group: Fluxo) - chart + sortable table.
    tabs.append(_build_fluxo_tab(obs_all))

    # Tabs 2-5: Per investor (group: Investidores).
    for investor, label in _INVESTORS:
        tabs.append(_build_investor_tab(obs_all, investor, label))

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[ddm.fluxo] Done! {len(tabs)} tabs, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
    }
