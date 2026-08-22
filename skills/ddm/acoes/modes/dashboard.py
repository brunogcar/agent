"""Mode: dashboard -- DDM acoes dashboard.

[v1] 1-tab dashboard:
  Tab 1. Acoes (group: Acoes)
    - 4 KPIs (total de acoes, mais negociada, maior alta, maior baixa)
    - Price distribution chart (column chart with 16 colored bars, one
      per price-range bucket from skills/_price_colors.py)
    - Sortable stocks table (Ticker | Nome | Negocios | Ultima (R$) | Variacao)
      with default sort by Negocios DESC.

Section titles don't repeat the skill name (already in tab name).
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.acoes._registry import register_mode
from skills.ddm.acoes.report import (
    build_kpi_card, build_stocks_table, build_distribution_chart,
    build_error_section,
)
from skills.ddm.acoes.helpers import format_int, format_pct
from data_sources.ddm.acoes.query_engine import (
    stocks_list, summary,
)


def _safe_call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_acoes_tab() -> dict:
    """Build the single Acoes tab with KPIs + distribution chart + sortable table."""
    kpis: list[dict] = []
    sections: list[dict] = []

    # Summary for KPIs (most traded / biggest gainer / biggest loser).
    summ = _safe_call(summary)
    if summ.get("status") == "ok":
        total = summ.get("total", 0)
        kpis.append(build_kpi_card(
            "Total de Acoes", total,
            subtitle="Acoes B3 listadas",
            formatted=format_int(total),
        ))

        mt = summ.get("most_traded") or {}
        if mt:
            kpis.append(build_kpi_card(
                "Mais Negociada",
                mt.get("ticker", ""),
                subtitle=f"{mt.get('name', '')} - {format_int(mt.get('negocios'))} negocios",
                formatted=mt.get("ticker", ""),
            ))

        bg = summ.get("biggest_gainer") or {}
        if bg:
            kpis.append(build_kpi_card(
                "Maior Alta",
                bg.get("variation"),
                subtitle=f"{bg.get('ticker', '')} - {bg.get('name', '')}",
                formatted=format_pct(bg.get("variation")),
            ))

        bl = summ.get("biggest_loser") or {}
        if bl:
            kpis.append(build_kpi_card(
                "Maior Baixa",
                bl.get("variation"),
                subtitle=f"{bl.get('ticker', '')} - {bl.get('name', '')}",
                formatted=format_pct(bl.get("variation")),
            ))
    else:
        sections.append(build_error_section(
            "Resumo", summ.get("error", "sem dados")))

    # Sortable stocks table (all stocks, default sort Negocios DESC).
    lst = _safe_call(stocks_list, order_by="negocios", direction="desc")
    stocks: list[dict] = []
    if lst.get("status") == "ok":
        stocks = lst.get("stocks", [])
        ref_date = stocks[0].get("ref_date", "") if stocks else ""

        # Price distribution chart (16 colored bars, one per price-range bucket).
        # Placed BEFORE the table per the task spec (KPIs -> chart -> table).
        prices = [s.get("last_price") for s in stocks]
        sections.append(build_distribution_chart(
            "Distribuicao de Precos",
            prices,
            description=(
                "Distribuicao das acoes B3 por faixa de preco (R$). "
                "Cada barra usa a cor da faixa correspondente (vermelho "
                "para precos baixos, verde para precos medios, azul para "
                "precos acima de R$100). A maioria das acoes B3 se "
                "concentra em faixas baixas (< R$50)."
            ),
        ))

        sections.append(build_stocks_table(
            "Acoes B3",
            stocks,
            description=(
                f"Lista de todas as acoes B3 listadas ({len(stocks)} no total). "
                f"Clique no cabecalho das colunas para ordenar asc/desc. "
                f"Ordem padrao: Negocios DESC."
                + (f" Data de referencia: {ref_date}." if ref_date else "")
            ),
        ))
    else:
        sections.append(build_error_section(
            "Acoes B3", lst.get("error", "sem dados")))

    return {
        "name":     "Acoes",
        "group":    "Acoes",
        "sections": sections,
        "_kpis":    kpis,
    }


@register_mode(
    "dashboard",
    description=(
        "DDM acoes dashboard. 1 tab: Acoes. Shows 4 KPIs (total de acoes, "
        "mais negociada, maior alta, maior baixa) + price distribution "
        "chart (16 colored bars, one per price-range bucket) + sortable "
        "stocks table (Ticker | Nome | Negocios | Ultima (R$) | Variacao). "
        "Click column headers to sort asc/desc. Default sort: Negocios DESC."
    ),
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="acoes", mode="dashboard")',
    ],
)
def dashboard() -> dict:
    _t0 = _dt.now()
    print(f"[ddm.acoes] Starting dashboard...", flush=True)

    tab = _build_acoes_tab()
    kpis = tab.pop("_kpis", [])
    tabs = [tab]

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[ddm.acoes] Done! {len(tabs)} tab, {len(kpis)} KPIs "
          f"in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
    }
