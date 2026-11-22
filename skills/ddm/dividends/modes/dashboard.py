"""Mode: dashboard — 4-tab DDM Proventos dashboard.

[v2] The Proventos reorganization (WebUI v1.18 family parity). The v1
static was 1 flat tab (4 KPIs + distribution chart + sortable table)
over the WHOLE agenda — and the agenda mixes B3 natives with BDRs
(tickers ending in 34: AAPL34, GDBR34...), whose payouts live in a
different value universe (R$ 1,70-6,32 vs natives topping at ~R$ 1,13).
The reorganization splits on that predicate and adds the two
aggregations the flat table hid:

Tabs:
  1. Proventos  (group: Proventos) — the B3 natives agenda: the
     distribution by value range (8 faixas, Dividendo vs JCP) + the
     Dividendo/JCP doughnut + the sortable agenda table.
  2. BDRs       (group: BDRs) — the *34 agenda: the same distribution
     chart + the BDR agenda table (one row per event).
  3. Por Empresa (group: Análise) — "quem paga?": the per-ticker
     aggregation (eventos, valor total/média/máximo, último pagamento),
     Top 10 by valor (B3/BDR colored) + Top 10 by eventos + the full
     empresas table with the BDR flag.
  4. Calendário (group: Análise) — "quando cai?": the per-day payments
     (valor por data, pago vs a pagar) + the per-day table (eventos,
     BDRs, principais pagadores).

Top-level KPIs (6) cover the WHOLE agenda (the static's flat KPI row —
fluxo v2 precedent): Total de Proventos (com o split B3/BDR no
subtitle), Empresas Pagadoras, Valor Total, Maior Provento, Valor
Mediano e Próximo Pagamento. The scoped KPIs live in the WebUI subtabs
(each subtab response carries its own kpis row).

When a sub-query fails (DB not synced, HTTP error), the dashboard still
returns status=ok with the failed tab containing an error section -
mirrors the CVM financials + bcb/macro + ddm/inflation/juros/poupanca/
acoes graceful-degradation contract.

Registered as "dashboard" in skills.ddm.dividends._registry.MODES.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.ddm.dividends._registry import register_mode
from skills.ddm.dividends.report import (
    build_kpi_card, build_dividends_table, build_distribution_chart,
    build_tipo_doughnut, build_top_empresas_chart, build_empresa_table,
    build_calendario_chart, build_calendario_table,
    build_error_section, _format_count,
)
from skills.ddm.dividends.helpers import (
    aggregate_by_day, aggregate_by_empresa, format_brl, format_date,
    is_bdr, summarize,
)
from data_sources.ddm.dividends.query_engine import dividends_list


def _safe_call(fn, **kwargs):
    """Call a query function and return its dict, or an error payload."""
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _fetch_agenda() -> tuple[list[dict], str]:
    """Fetch the full agenda (value DESC).

    Returns (dividends, error_message) — exactly one is non-empty.
    """
    resp = _safe_call(dividends_list, order_by="value", direction="desc")
    if resp.get("status") == "ok":
        return resp.get("dividends", []), ""
    return [], resp.get("error", "sem dados — rode sync_all primeiro")


def _build_kpis(whole: list[dict], summ: dict, today_iso: str) -> list[dict]:
    """Build the 6 top-level KPI cards (the WHOLE agenda — natives+BDRs).

    `summ` comes from the shared helpers.summarize (the SAME function
    the WebUI Proventos family uses — no forked numerics).

    KPIs:
      1. Total de Proventos   - count of all events (B3/BDR split in the
                                subtitle — the one-glance BDR share)
      2. Empresas Pagadoras   - distinct tickers in the agenda
      3. Valor Total          - sum of all per-share values (R$)
      4. Maior Provento       - biggest single event (ticker + value)
      5. Valor Mediano        - median per-share value (the center the
                                BDR outliers don't pull)
      6. Próximo Pagamento    - next payment_date (DD/MM/YYYY)
    """
    if not whole:
        return [
            build_kpi_card("Total de Proventos", "-"),
            build_kpi_card("Empresas Pagadoras", "-"),
            build_kpi_card("Valor Total", "-"),
            build_kpi_card("Maior Provento", "-"),
            build_kpi_card("Valor Mediano", "-"),
            build_kpi_card("Próximo Pagamento", "-"),
        ]

    n_bdr = sum(1 for d in whole if is_bdr(d.get("ticker", "")))
    biggest = summ.get("biggest") or {}
    biggest_value_str = format_brl(biggest.get("value")) \
        if biggest.get("ticker") else "-"
    biggest_subtitle = (f"{biggest.get('ticker', '')} "
                        f"({biggest.get('tipo', '')})") \
        if biggest.get("ticker") else ""

    next_pay = summ.get("next_payment_date") or ""
    next_pay_display = format_date(next_pay) if next_pay else "-"

    return [
        build_kpi_card(
            "Total de Proventos",
            _format_count(summ.get("total", 0)),
            subtitle=(f"B3: {_format_count(summ.get('total', 0) - n_bdr)} "
                      f"| BDR: {_format_count(n_bdr)} — "
                      f"Dividendo: {_format_count(summ.get('by_tipo', {}).get('Dividendo', 0))}, "
                      f"JCP: {_format_count(summ.get('by_tipo', {}).get('JCP', 0))}"),
        ),
        build_kpi_card(
            "Empresas Pagadoras",
            _format_count(summ.get("tickers", 0)),
            subtitle="empresas/tickers distintos com evento na agenda",
        ),
        build_kpi_card(
            "Valor Total",
            format_brl(summ.get("total_value", 0.0)),
            subtitle="soma dos valores por ação — valores por ação de empresas diferentes não se somam em caixa; é a leitura de escala da agenda",
        ),
        build_kpi_card(
            "Maior Provento",
            biggest_value_str,
            subtitle=biggest_subtitle,
        ),
        build_kpi_card(
            "Valor Mediano",
            format_brl(summ.get("median_value", 0.0)),
            subtitle="metade dos eventos paga menos que isso (a mediana é o centro que os outliers BDR não puxam)",
        ),
        build_kpi_card(
            "Próximo Pagamento",
            next_pay_display,
            subtitle="data de pagamento" if next_pay else "",
        ),
    ]


def _build_proventos_tab(natives: list[dict]) -> dict:
    """Tab 1: the B3 natives agenda (the 'main display')."""
    sections: list[dict] = []
    if not natives:
        sections.append(build_error_section(
            "Proventos", "sem proventos B3 para exibir"))
    else:
        sections.append(build_distribution_chart(
            "Distribuição por Faixa de Valor",
            natives,
            description=(
                "Quantidade de proventos B3 por faixa de valor (R$), "
                "agrupada por tipo (Dividendo vs JCP). Faixas: "
                "<0,05 | 0,05-0,10 | 0,10-0,25 | 0,25-0,50 | 0,50-1,00 | "
                "1,00-2,00 | 2,00-5,00 | ≥5,00. Barras lado a lado "
                "(NÃO empilhadas)."),
        ))
        sections.append(build_tipo_doughnut(
            "Dividendo vs JCP",
            natives,
            description=(
                "A divisão dos eventos B3 por tipo — Dividendo (teal) vs "
                "JCP, Juros sobre Capital Próprio (âmbar). O JCP é o "
                "provento com crédito tributário de IR, o dividendo é "
                "isento para a pessoa física."),
        ))
        sections.append(build_dividends_table(
            "Agenda de Proventos B3",
            natives,
            description=(
                f"Os {len(natives)} proventos das ações B3 (sem BDRs). "
                "Clique no cabeçalho de qualquer coluna para ordenar "
                "(clicar novamente alterna asc/desc). Ordenação padrão: "
                "Valor DESC. Valores em R$ (decimal PT-BR). Datas em "
                "DD/MM/AAAA. Tipo: Dividendo | JCP (Juros sobre Capital "
                "Próprio). Os proventos dos BDRs estão na aba BDRs."),
        ))
    return {"name": "Proventos", "group": "Proventos", "sections": sections}


def _build_bdrs_tab(bdrs: list[dict]) -> dict:
    """Tab 2: the BDR agenda (tickers ending in 34)."""
    sections: list[dict] = []
    if not bdrs:
        sections.append(build_error_section(
            "BDRs", "sem BDRs na agenda atual"))
    else:
        sections.append(build_distribution_chart(
            "Distribuição por Faixa de Valor — BDRs",
            bdrs,
            description=(
                "A mesma escala de 8 faixas, agora só com os BDRs "
                "(Brazilian Depositary Receipts — ações de empresas "
                "estrangeiras negociadas na B3, tickers terminados em 34). "
                "Os pagamentos por recibo vivem num universo de valor "
                "próprio: é por isso que a distribuição estica para a "
                "direita (faixas 1,00-2,00 / 2,00-5,00 / ≥5,00) enquanto "
                "a das ações B3 se concentra abaixo de R$ 1,00."),
        ))
        sections.append(build_dividends_table(
            "Agenda de Proventos — BDRs",
            bdrs,
            description=(
                f"Os {len(bdrs)} proventos dos BDRs. A coluna Código "
                "destacada (cinza) marca o ticker BDR. Mesmo contrato da "
                "tabela B3: ordenável por coluna, padrão Valor DESC."),
        ))
    return {"name": "BDRs", "group": "BDRs", "sections": sections}


def _build_empresa_tab(empresas: list[dict], n_bdr_events: int,
                       total_events: int) -> dict:
    """Tab 3: the per-empresa aggregation ('quem paga?')."""
    sections: list[dict] = []
    if not empresas:
        sections.append(build_error_section(
            "Por Empresa", "sem empresas para exibir"))
    else:
        sections.append(build_top_empresas_chart(
            "Top 10 Empresas — Valor Total",
            empresas, metric="value",
            description=(
                "As 10 maiores pagadoras da agenda por valor somado (R$ "
                "por ação/cota). Cada barra na cor da sua classe — B3 "
                "(teal) vs BDR (cinza): o topo do ranking de valor é "
                "dominado por BDRs, a leitura que a tabela única do v1 "
                "escondia."),
        ))
        sections.append(build_top_empresas_chart(
            "Top 10 Empresas — Nº de Eventos",
            empresas, metric="events",
            description=(
                "As 10 empresas com mais eventos na agenda (a atividade "
                "recorrente — quem paga várias vezes no mês), na mesma "
                "paleta B3/BDR."),
        ))
        sections.append(build_empresa_table(
            "Todas as Empresas",
            empresas,
            description=(
                f"A agenda agregada por empresa: {len(empresas)} "
                "pagadoras — eventos, valor total, média, máximo e o "
                "último pagamento. Tickers BDR destacados em cinza (com "
                "o ⓘ explicando). Ordenação padrão: Valor Total DESC."),
        ))
    return {"name": "Por Empresa", "group": "Análise",
            "sections": sections}


def _build_calendario_tab(days: list[dict], today_iso: str) -> dict:
    """Tab 4: the per-day payments ('quando cai?')."""
    sections: list[dict] = []
    if not days:
        sections.append(build_error_section(
            "Calendário", "sem datas de pagamento na agenda"))
    else:
        sections.append(build_calendario_chart(
            "Pagamentos por Dia",
            days, today_iso=today_iso,
            description=(
                "O valor a pagar por data de pagamento — já pago (teal) "
                "vs a pagar (âmbar, a partir de hoje). A agenda é uma "
                "janela móvel: cada sincronização da fonte ddm-dividends "
                "traz o mês corrente."),
        ))
        sections.append(build_calendario_table(
            "Calendário de Pagamentos",
            days,
            description=(
                "Um dia por linha: eventos, quantos são BDRs, o valor "
                "total e os principais pagadores (o ⓘ da data carrega o "
                "top-3 do dia). Ordenação padrão: Data DESC (mais "
                "recentes primeiro)."),
        ))
    return {"name": "Calendário", "group": "Análise", "sections": sections}


@register_mode(
    "dashboard",
    description=(
        "DDM Proventos dashboard - 4 tabs: Proventos (B3 natives), BDRs, "
        "Por Empresa, Calendário. The agenda de dividendos split by asset "
        "class (BDR tickers end in 34), aggregated by empresa (events, "
        "total/avg/max value, last payment) and by payment day (pago vs a "
        "pagar). Top-level KPIs: total, empresas pagadoras, valor total, "
        "maior provento, valor mediano, próximo pagamento. Distribution "
        "chart: 8 value-range buckets, Dividendo vs JCP. Tables sortable "
        "(Valor DESC default). Dates DD/MM/AAAA (PT-BR)."
    ),
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="ddm", sub_domain="dividends", mode="dashboard")',
    ],
)
def dashboard() -> dict:
    """Build the 4-tab DDM Proventos dashboard.

    KPIs are at the top level (mirrors the bcb/macro + ddm/* dashboard
    contract) and cover the WHOLE agenda; the per-scope (B3/BDR) KPI
    rows live in the WebUI Proventos family subtabs.
    """
    _t0 = _dt.now()
    print(f"[ddm.dividends] Starting dashboard...", flush=True)

    divs, err = _fetch_agenda()
    today_iso = _dt.now().strftime("%Y-%m-%d")

    natives = [d for d in divs if not is_bdr(d.get("ticker", ""))]
    bdrs = [d for d in divs if is_bdr(d.get("ticker", ""))]

    kpis = _build_kpis(divs, summarize(divs, today_iso), today_iso)

    tabs: list[dict] = []
    if not divs:
        tabs.append({"name": "Proventos", "group": "Proventos",
                     "sections": [build_error_section("Proventos", err)]})
    else:
        tabs.append(_build_proventos_tab(natives))
        tabs.append(_build_bdrs_tab(bdrs))
        tabs.append(_build_empresa_tab(
            aggregate_by_empresa(divs), len(bdrs), len(divs)))
        tabs.append(_build_calendario_tab(
            aggregate_by_day(divs), today_iso))

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
