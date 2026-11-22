"""Mode: dashboard -- DDM acoes dashboard.

[v1] 1-tab dashboard:
  Tab 1. Acoes (group: Acoes)
    - 4 KPIs (total de acoes, mais negociada, maior alta, maior baixa)
    - Price distribution chart (column chart with 22 colored bars, one
      per price-range bucket from skills/_colors/price.py — the palette's
      v2 grew the original 16 to 22 with the 100–300+ blue tail)
    - Sortable stocks table (Ticker | Nome | Negócios | Última (R$) |
      Variação) with default sort by Negócios DESC.

[v2] + the EVOLUTION of the distribution over time — the /acoes page is a
  live quote table with NO history, so the series comes from the
  stocks_history snapshots accumulated by every sync (one per day, keyed
  by (ref_date, ticker) — see data_sources/ddm/acoes/sync_engine.py):
    - 2 stacked-area charts over the snapshot dates: the % of total per
      range (100% stacked — the reference chart style; the bands sum to
      exactly 100% on every date) + the absolute count per range. One
      dataset per range in the palette's color, lowest prices at the
      bottom; tooltips use interaction 'nearest' (22 bands × index mode
      would be a wall of tooltip rows); both carry the range selector.
    - Fewer than 2 stored snapshots degrade to a text note explaining how
      the history accumulates (the empty case falls back to the CURRENT
      stocks snapshot as the first point — that is exactly what the next
      sync preserves).

[v2] PT-BR accents in every user-facing string ("Ações", "Negócios",
  "Distribuição de Preços", ...) — the juros/inflation statics write
  proper PT-BR; the acoes v1 strings were ASCII-fied.

Section titles don't repeat the skill name (already in tab name).
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.acoes._registry import register_mode
from skills.ddm.acoes.report import (
    build_kpi_card, build_stocks_table, build_distribution_chart,
    build_evolution_sections, build_history_note_section,
    build_error_section,
)
from skills.ddm.acoes.helpers import format_int, format_pct
from data_sources.ddm.acoes.query_engine import (
    stocks_list, summary, price_history,
)


def _safe_call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _build_acoes_tab() -> dict:
    """Build the single Acoes tab: KPIs + distribution + evolution + table."""
    kpis: list[dict] = []
    sections: list[dict] = []

    # Summary for KPIs (most traded / biggest gainer / biggest loser).
    summ = _safe_call(summary)
    if summ.get("status") == "ok":
        total = summ.get("total", 0)
        kpis.append(build_kpi_card(
            "Total de Ações", total,
            subtitle="Ações B3 listadas",
            formatted=format_int(total),
        ))

        mt = summ.get("most_traded") or {}
        if mt:
            kpis.append(build_kpi_card(
                "Mais Negociada",
                mt.get("ticker", ""),
                subtitle=f"{mt.get('name', '')} — {format_int(mt.get('negocios'))} negócios",
                formatted=mt.get("ticker", ""),
            ))

        bg = summ.get("biggest_gainer") or {}
        if bg:
            kpis.append(build_kpi_card(
                "Maior Alta",
                bg.get("variation"),
                subtitle=f"{bg.get('ticker', '')} — {bg.get('name', '')}",
                formatted=format_pct(bg.get("variation")),
            ))

        bl = summ.get("biggest_loser") or {}
        if bl:
            kpis.append(build_kpi_card(
                "Maior Baixa",
                bl.get("variation"),
                subtitle=f"{bl.get('ticker', '')} — {bl.get('name', '')}",
                formatted=format_pct(bl.get("variation")),
            ))
    else:
        sections.append(build_error_section(
            "Resumo", summ.get("error", "sem dados")))

    # Sortable stocks table (all stocks, default sort Negócios DESC).
    lst = _safe_call(stocks_list, order_by="negocios", direction="desc")
    stocks: list[dict] = []
    if lst.get("status") == "ok":
        stocks = lst.get("stocks", [])
        ref_date = stocks[0].get("ref_date", "") if stocks else ""

        # Price distribution chart (22 colored bars, one per price-range
        # bucket). Placed BEFORE the table per the task spec (KPIs ->
        # chart -> table).
        prices = [s.get("last_price") for s in stocks]
        sections.append(build_distribution_chart(
            "Distribuição de Preços",
            prices,
            description=(
                "Distribuição das ações B3 por faixa de preço (R$). "
                "Cada barra usa a cor da faixa correspondente (vermelho "
                "para preços baixos, verde para preços médios, azul para "
                "preços acima de R$ 100). A maioria das ações B3 se "
                "concentra em faixas baixas (< R$ 50)."
            ),
        ))

        sections.append(build_stocks_table(
            "Ações B3",
            stocks,
            description=(
                f"Lista de todas as ações B3 listadas ({len(stocks)} no total). "
                f"Clique no cabeçalho das colunas para ordenar asc/desc. "
                f"Ordem padrão: Negócios DESC."
                + (f" Data de referência: {ref_date}." if ref_date else "")
            ),
        ))
    else:
        sections.append(build_error_section(
            "Ações B3", lst.get("error", "sem dados")))

    # ── [v2] Evolution of the distribution over time ─────────────────────
    # The stored snapshots (one per sync day). Empty history falls back to
    # the CURRENT stocks snapshot as a single point — that is exactly what
    # the next sync preserves into stocks_history.
    hist = _safe_call(price_history)
    dates: list[str] = []
    prices_by_date: list[list] = []
    if hist.get("status") == "ok" and hist.get("snapshots", 0) > 0:
        dates = hist["dates"]
        prices_by_date = hist["prices"]
    elif stocks:
        ref_date = stocks[0].get("ref_date", "") if stocks else ""
        dates = [ref_date] if ref_date else []
        prices_by_date = [[s.get("last_price") for s in stocks]] if dates else []

    if len(dates) >= 2:
        sections.extend(build_evolution_sections(
            dates, prices_by_date,
            description=(
                f"{len(dates)} snapshots diários armazenados "
                f"({dates[0]} a {dates[-1]})."
            ),
        ))
    else:
        sections.append(build_history_note_section(
            len(dates), dates[0] if dates else ""))

    return {
        "name":     "Ações",
        "group":    "Ações",
        "sections": sections,
        "_kpis":    kpis,
    }


@register_mode(
    "dashboard",
    description=(
        "DDM acoes dashboard. 1 tab: Acoes. Shows 4 KPIs (total de ações, "
        "mais negociada, maior alta, maior baixa) + price distribution "
        "chart (22 colored bars, one per price-range bucket) + the "
        "EVOLUTION of the distribution over time (2 stacked-area charts "
        "over the daily snapshots accumulated in stocks_history — % do "
        "total 100% empilhado + nº absoluto) + sortable stocks table "
        "(Ticker | Nome | Negócios | Última (R$) | Variação). Click "
        "column headers to sort asc/desc. Default sort: Negócios DESC."
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
