"""Mode: dashboard -- 1-tab DDM dividends dashboard.

Tab:
  1. Dividendos  (group: Dividendos) - KPIs + distribution chart + sortable table

The Dividendos tab contains:
  - 4 KPI cards (total dividendos, valor total, maior dividendo, proximo
    pagamento) - promoted to top level via _kpis
  - Distribution chart (grouped bar: Dividendo vs JCP per value range,
    8 buckets: <0,05 / 0,05-0,10 / 0,10-0,25 / 0,25-0,50 / 0,50-1,00 /
    1,00-2,00 / 2,00-5,00 / >=5,00)
  - Sortable dividends table (default sort: Valor DESC; columns: Codigo |
    Tipo | Valor (R$) | Registro | Ex | Pagamento; dates displayed as
    DD/MM/YYYY PT-BR; NO price colors on Valor - dividend amounts, not
    stock prices).

When a sub-query fails (DB not synced, HTTP error), the dashboard still
returns status=ok with the failed tab containing an error section - mirrors
the CVM financials + bcb/macro + ddm/inflation/juros/poupanca graceful-
degradation contract.

Registered as "dashboard" in skills.ddm.dividends._registry.MODES.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.dividends._registry import register_mode
from skills.ddm.dividends.report import (
    build_kpi_card, build_dividends_table, build_distribution_chart,
    build_error_section, _format_count,
)
from skills.ddm.dividends.helpers import format_brl, format_date
from data_sources.ddm.dividends.query_engine import (
    dividends_list, summary,
)


def _safe_call(fn, **kwargs):
    """Call a query function and return its dict, or an error payload."""
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_kpis(summ: dict) -> list[dict]:
    """Build the 4 top-level KPI cards from the summary() payload.

    KPIs:
      1. Total de dividendos   - count of all dividend rows
      2. Valor total           - sum of all dividend values (R$)
      3. Maior dividendo       - biggest single dividend (ticker + value)
      4. Proximo pagamento     - next payment_date (DD/MM/YYYY)
    """
    if summ.get("status") != "ok":
        return [
            build_kpi_card("Total de dividendos", "-"),
            build_kpi_card("Valor total", "-"),
            build_kpi_card("Maior dividendo", "-"),
            build_kpi_card("Proximo pagamento", "-"),
        ]

    biggest = summ.get("biggest") or {}
    biggest_label = ""
    if biggest.get("ticker"):
        biggest_label = biggest["ticker"]
        biggest_value_str = format_brl(biggest.get("value"))
        biggest_subtitle = f"{biggest_label}: {biggest_value_str}"
    else:
        biggest_subtitle = ""
        biggest_value_str = "-"

    next_pay = summ.get("next_payment_date") or ""
    next_pay_display = format_date(next_pay) if next_pay else "-"

    return [
        build_kpi_card(
            "Total de dividendos",
            _format_count(summ.get("total_dividends", 0)),
            subtitle=f"Dividendo: {_format_count(summ.get('by_tipo', {}).get('Dividendo', 0))} | "
                     f"JCP: {_format_count(summ.get('by_tipo', {}).get('JCP', 0))}",
        ),
        build_kpi_card(
            "Valor total",
            format_brl(summ.get("total_value", 0.0)),
            subtitle="soma de todos os dividendos",
        ),
        build_kpi_card(
            "Maior dividendo",
            biggest_value_str,
            subtitle=biggest_subtitle,
        ),
        build_kpi_card(
            "Proximo pagamento",
            next_pay_display,
            subtitle=f"data de pagamento" if next_pay else "",
        ),
    ]


def _build_distribution_section(divs: list[dict]) -> dict:
    """Build the grouped-bar distribution chart section."""
    if not divs:
        return build_error_section(
            "Distribuicao por faixa de valor",
            "sem dividendos para exibir")
    return build_distribution_chart(
        "Distribuicao por faixa de valor",
        divs,
        description=("Quantidade de dividendos por faixa de valor (R$), "
                     "agrupada por tipo (Dividendo vs JCP). Faixas: "
                     "<0,05 | 0,05-0,10 | 0,10-0,25 | 0,25-0,50 | "
                     "0,50-1,00 | 1,00-2,00 | 2,00-5,00 | >=5,00. "
                     "Barras lado a lado (NAO empilhadas)."),
    )


def _build_dividends_table_section(divs: list[dict]) -> dict:
    """Build the sortable dividends table section.

    Default sort: Valor DESC (column index 2, 0-indexed). Click any column
    header to re-sort; click again to toggle asc/desc.
    """
    if not divs:
        return build_error_section(
            "Dividendos",
            "sem dividendos para exibir")
    return build_dividends_table(
        "Dividendos",
        divs,
        description=("Agenda de dividendos. Clique no cabecalho de qualquer "
                     "coluna para ordenar (clicar novamente alterna "
                     "asc/desc). Ordenacao padrao: Valor DESC. Valores em "
                     "R$ (decimal PT-BR). Datas em DD/MM/AAAA. Tipo: "
                     "Dividendo | JCP (Juros sobre Capital Proprio)."),
    )


def _build_dividendos_tab() -> tuple[dict, list[dict]]:
    """Build the Dividendos tab.

    Returns (tab, kpis):
      tab  - tab dict {"name": "Dividendos", "group": "Dividendos",
                       "sections": [<chart>, <table>]}
      kpis - list of 4 KPI cards (empty on failure)
    """
    summ = _safe_call(summary)
    kpis = _build_kpis(summ)

    # Fetch all dividends (default sort: value desc — the table will re-sort
    # client-side via the sortable feature, so we just need the raw rows).
    divs_resp = _safe_call(dividends_list, order_by="value", direction="desc")
    if divs_resp.get("status") == "ok":
        divs = divs_resp.get("dividends", [])
    else:
        divs = []

    sections: list[dict] = []
    if not divs:
        sections.append(build_error_section(
            "Dividendos",
            divs_resp.get("error", "sem dados - rode sync_all primeiro")))
    else:
        sections.append(_build_distribution_section(divs))
        sections.append(_build_dividends_table_section(divs))

    tab = {
        "name":     "Dividendos",
        "group":    "Dividendos",
        "sections": sections,
    }
    return tab, kpis


@register_mode(
    "dashboard",
    description=(
        "DDM dividends dashboard - 1 tab: Dividendos. The tab shows 4 KPIs "
        "(total dividendos, valor total, maior dividendo, proximo pagamento) "
        "+ grouped bar distribution chart (Dividendo vs JCP per value range) "
        "+ sortable dividends table (default sort: Valor DESC). Click column "
        "headers to re-sort. Dates displayed as DD/MM/AAAA (PT-BR)."
    ),
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="dividends", mode="dashboard")',
    ],
)
def dashboard() -> dict:
    """Build the 1-tab DDM dividends dashboard.

    KPIs are at the top level (mirrors the bcb/macro + ddm/* dashboard
    contract).
    """
    _t0 = _dt.now()
    print(f"[ddm.dividends] Starting dashboard...", flush=True)

    tab, kpis = _build_dividendos_tab()
    tabs: list[dict] = [tab]

    errors = []
    for t in tabs:
        for s in t.get("sections", []):
            if s.get("type") == "text" and \
                    "Erro ao consultar" in s.get("body", ""):
                errors.append(f"{t['name']}: {s['body']}")

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[ddm.dividends] Done! {len(tabs)} tabs, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
        "errors": errors,
    }
