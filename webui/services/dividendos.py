"""webui/services/dividendos.py — Mercado page / Proventos family data service (DDM).

[v1.18] The Proventos family of the ``/webui/mercado`` page — a reorganized
take on the static ``dividends_dashboard.html`` reference (built by
skills/ddm/dividends/modes/dashboard.py: 1 flat tab — 4 KPIs + the
8-bucket distribution chart + the sortable agenda table over the WHOLE
agenda). Seventh family of the Mercado page (focus v1.12, fluxo v1.13,
índices v1.14, inflação v1.15, juros v1.16, ações v1.17) — the agenda de
dividendos (~94 events:
Código | Tipo | Valor (R$) | Registro | Ex | Pagamento; Dividendo vs JCP).

The headline of v1.18 is the BDR SPLIT: the agenda mixes B3 natives with
BDRs (Brazilian Depositary Receipts — foreign companies' shares traded on
B3, tickers ending in "34": AAPL34, GDBR34...), and their payouts live in
a different value universe (R$ 1,70-6,32 vs natives topping at ~R$ 1,13)
— 39 of ~94 events. The single flat table hid that; every view now
splits on the predicate.

Per the v1.8–v1.17 reorganization spirit the static's gaps get fixed,
not copied:

  overview → "o que a agenda B3 paga?"        (os 4 KPIs do estático,
              escopados às ações B3 + Empresas Pagadoras e Valor
              Mediano; a distribuição nas 8 faixas + o doughnut
              Dividendo/JCP + a tabela completa — os BDRs ficam na
              subaba BDRs)
  bdrs     → "e os BDRs?"                     (inédita: o mesmo
              tratamento para os recibos *34 — os pagamentos por
              recibo esticam a distribuição para a direita)
  empresas → "quem paga?"                     (inédita: a agenda
              agregada por empresa — eventos, valor total/média/máximo,
              último pagamento; Top 10 por valor e por eventos, as
              barras coloridas por classe B3/BDR)
  calendario → "quando cai?"                  (inédita: os pagamentos
              por dia — pago vs a pagar — + a tabela por data com os
              principais pagadores do dia)

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.dividends.query_engine`` (memory_db/ddm/
    dividends.db — dividends: ~94 rows, the rolling monthly agenda)

Numerics = the skill's shared helpers (``skills/ddm/dividends/
helpers.py``): ``is_bdr`` (the *34 predicate), ``summarize`` (the scoped
KPI numbers), ``bucketize`` (the 8 value-range buckets),
``aggregate_by_empresa`` + ``aggregate_by_day`` — the same functions the
static dashboard uses; ``format_brl`` / ``format_int`` / ``format_date``
for the PT-BR display strings. No forked numerics.

Naming: the FAMILY display name is "Proventos" (the PT-BR umbrella for
dividends + JCP + rendimentos — the term the company tab already uses);
the registry family key is "dividendos" (the data source's name — the
company page's proventos:* keys are taken, and the family key names the
DATA, the pill names the VIEW).

Data conventions (v1.8 fix1 / v1.9–v1.17 lineage):
  - Table dates dd/mm/yyyy (sortable — _valSortKey parses that form);
    the calendário chart labels ship ISO "YYYY-MM-DD" on purpose —
    renderValChart formats date axes + tooltips client-side.
  - Every number is a PRE-FORMATTED PT-BR string — the client only
    colorizes (negative red, % green).
  - Degradation: missing/empty dividends.db → PT-BR ``_error`` naming
    the ``ddm-dividends`` source exactly as the Sincronização page
    lists it (DDM — dividendos).
"""
from __future__ import annotations

from datetime import datetime as _dt
from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    kpi,
    table_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.ddm.dividends.query_engine import (
    dividends_list as _dividends_list,
)

# ── the skill's display + numerics helpers (no forked numerics) ─────────────
from skills.ddm.dividends.helpers import (
    aggregate_by_day as _by_day,
    aggregate_by_empresa as _by_empresa,
    bucketize as _bucketize,
    format_brl as _brl,             # "R$ 0,017250" / "-" for None
    format_date as _fmt_data,       # "2026-11-15" → "15/11/2026"
    format_int as _int,             # "1.234"
    is_bdr as _is_bdr,
    summarize as _summarize,
)

_ERR = ("Agenda de proventos indisponível — sincronize a fonte "
        "ddm-dividends (DDM — dividendos) na "
        "página Sincronização.")

# The tipo palette (Dividendo teal / JCP amber) + the BDR slate accent —
# deliberately NOT teal/amber so "é BDR" can never be misread as a tipo.
_C_DIV = "#0d9488"
_C_JCP = "#f59e0b"
_C_BDR = "#94a3b8"


# ── helpers ─────────────────────────────────────────────────────────────────
def _agenda() -> list[dict[str, Any]] | None:
    """The full agenda (Valor DESC); None on any failure."""
    try:
        res = _dividends_list(order_by="value", direction="desc")
    except Exception:
        return None
    if res.get("status") != "ok":
        return None
    divs = res.get("dividends") or []
    return divs or None


def _plain_pct(v: float, decimals: int = 1) -> str:
    """41.49 → '41,5%' (unsigned, PT-BR comma)."""
    return f"{v:.{decimals}f}".replace(".", ",") + "%"


def _split(agenda: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """(natives, bdrs) — the BDR predicate applied once."""
    natives = [d for d in agenda if not _is_bdr(d.get("ticker", ""))]
    bdrs = [d for d in agenda if _is_bdr(d.get("ticker", ""))]
    return natives, bdrs


def _distribution_chart(title: str, divs: list[dict[str, Any]],
                        description: str) -> dict[str, Any]:
    """The 8-bucket grouped bar (Dividendo vs JCP) — the static's chart."""
    b = _bucketize(divs)
    return chart_section(
        title,
        {
            "type": "bar",
            "data": {
                "labels": b["labels"],
                "datasets": [
                    {"label": "Dividendo", "data": b["dividendo"],
                     "backgroundColor": _C_DIV},
                    {"label": "JCP", "data": b["jcp"],
                     "backgroundColor": _C_JCP},
                ],
            },
            "options": {
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"title": {"display": True,
                                    "text": "Faixa de valor (R$)"}},
                    "y": {"title": {"display": True,
                                    "text": "Quantidade de proventos"},
                          "beginAtZero": True},
                },
                "tooltipUnit": " proventos",
            },
        },
        description=description,
    )


def _agenda_table(title: str, divs: list[dict[str, Any]],
                  description: str, note: str) -> dict[str, Any]:
    """The sortable agenda table (the static's, tooltip on the ticker)."""
    rows: list[list[Any]] = []
    for d in divs:
        ticker = d.get("ticker", "") or ""
        tip = ""
        if _is_bdr(ticker):
            tip = ("BDR — Brazilian Depositary Receipt (empresa "
                   "estrangeira negociada na B3).")
        rows.append([
            {"text": ticker, "tooltip": tip} if tip else ticker,
            d.get("tipo", "") or "—",
            _brl(d.get("value")),
            _fmt_data(d.get("record_date", "")) or "—",
            _fmt_data(d.get("ex_date", "")) or "—",
            _fmt_data(d.get("payment_date", "")) or "—",
        ])
    tbl = table_section(
        title,
        ["Código", "Tipo", "Valor (R$)", "Registro", "Ex", "Pagamento"],
        rows,
        description=description,
        note=note,
    )
    tbl["sortable"] = True
    return tbl


def _top_empresas_chart(title: str, empresas: list[dict[str, Any]],
                        metric: str, description: str) -> dict[str, Any]:
    """Top 10 empresas bar — B3 (teal) vs BDR (slate) datasets."""
    key = (lambda e: e.get("total_value") or 0.0) if metric == "value" \
        else (lambda e: e.get("events") or 0)
    top = sorted(empresas, key=key, reverse=True)[:10]
    labels = [e["ticker"] for e in top]
    b3 = [round(key(e), 6) if not e["is_bdr"] else None for e in top]
    bdr = [round(key(e), 6) if e["is_bdr"] else None for e in top]
    y_title = "Valor somado (R$)" if metric == "value" else "Nº de eventos"
    return chart_section(
        title,
        {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "B3", "data": b3,
                     "backgroundColor": _C_DIV},
                    {"label": "BDR", "data": bdr,
                     "backgroundColor": _C_BDR},
                ],
            },
            "options": {
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "y": {"title": {"display": True, "text": y_title},
                          "beginAtZero": True},
                },
                "tooltipUnit": " R$" if metric == "value" else " eventos",
            },
        },
        description=description,
    )


# ── service ─────────────────────────────────────────────────────────────────
class DividendosService:
    """Mercado page / Proventos family — 4 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral (B3 natives — the "main display") ──────────────────────
    def overview(self) -> dict[str, Any]:
        """O que a agenda B3 paga — os proventos das ações listadas.

        Landing subtab: the static's whole 1-tab content, scoped to the
        B3 natives (the BDRs have their own subtab) — the KPIs grow from
        4 to 6 (Empresas Pagadoras + Valor Mediano), the distribution
        keeps the 8 faixas, and the Dividendo/JCP doughnut is NEW.
        """
        agenda = _agenda()
        if agenda is None:
            return error_payload("", _ERR)
        natives, bdrs = _split(agenda)
        if not natives:
            return error_payload(
                "", "Sem proventos B3 na agenda atual — a janela pode "
                "estar vazia; sincronize a fonte ddm-dividends ou "
                "consulte a subaba BDRs.")
        summ = _summarize(natives)
        b = _bucketize(natives)

        # ── KPIs (6) ────────────────────────────────────────────────────────
        biggest = summ.get("biggest") or {}
        kpis: list[dict[str, Any]] = [
            kpi("Total de Proventos B3", _int(summ["total"]),
                f"Dividendo: {_int(summ['by_tipo']['Dividendo'])} | "
                f"JCP: {_int(summ['by_tipo']['JCP'])}. Os "
                f"{_int(len(bdrs))} proventos dos BDRs (tickers "
                "terminados em 34) estão na subaba BDRs."),
            kpi("Empresas Pagadoras", _int(summ["tickers"]),
                "Tickers B3 distintos com evento na agenda."),
            kpi("Valor Total", _brl(summ["total_value"]),
                "Soma dos valores por ação — empresas diferentes não se "
                "somam em caixa; é a leitura de escala da agenda."),
        ]
        if biggest.get("ticker"):
            kpis.append(kpi(
                "Maior Provento", _brl(biggest["value"]),
                f"{biggest['ticker']} ({biggest['tipo']}) — pagamento em "
                f"{_fmt_data(biggest.get('payment_date', ''))}."))
        if summ["median_value"] is not None:
            kpis.append(kpi(
                "Valor Mediano", _brl(summ["median_value"]),
                "Metade dos eventos paga menos que isso — o centro que "
                "os outliers não puxam (média: "
                f"{_brl(summ['mean_value'])})."))
        if summ["next_payment_date"]:
            kpis.append(kpi(
                "Próximo Pagamento", _fmt_data(summ["next_payment_date"]),
                "A próxima data de pagamento da agenda B3."))

        # ── Sections ────────────────────────────────────────────────────────
        below_1 = sum(b["totals"][:5])
        sections: list[dict[str, Any]] = [
            _distribution_chart(
                "Distribuição por Faixa de Valor",
                natives,
                "A quantidade de proventos B3 por faixa de valor (R$), "
                "agrupada por tipo — Dividendo (teal) vs JCP (âmbar). "
                "Faixas: <0,05 | 0,05-0,10 | 0,10-0,25 | 0,25-0,50 | "
                "0,50-1,00 | 1,00-2,00 | 2,00-5,00 | ≥5,00 — barras "
                "lado a lado (não empilhadas). Abaixo de R$ 1,00: "
                f"{_plain_pct(100.0 * below_1 / summ['total']) if summ['total'] else '-'} "
                "dos eventos."),
            chart_section(
                "Dividendo vs JCP",
                {
                    "type": "doughnut",
                    "data": {
                        "labels": ["Dividendo", "JCP"],
                        "datasets": [{
                            "label": "Proventos",
                            "data": [summ["by_tipo"]["Dividendo"],
                                     summ["by_tipo"]["JCP"]],
                            "backgroundColor": [_C_DIV, _C_JCP],
                        }],
                    },
                    "options": {
                        "cutout": "45%",
                        "plugins": {"legend": {"display": True,
                                               "position": "top"}},
                        "tooltipUnit": " eventos",
                    },
                },
                description=(
                    "A divisão dos eventos por tipo — o JCP (Juros sobre "
                    "Capital Próprio) tem crédito tributário de IR; o "
                    "dividendo é isento para a pessoa física."
                ),
            ),
            _agenda_table(
                "Agenda de Proventos B3",
                natives,
                f"Os {_int(len(natives))} proventos das ações B3 (sem "
                "BDRs). Clique no cabeçalho para ordenar (padrão: Valor "
                "DESC); datas em dd/mm/aaaa.",
                "A agenda é uma janela móvel: cada sincronização da "
                "fonte ddm-dividends traz o mês corrente. Os BDRs "
                "reciprocam na subaba BDRs; as agregações por empresa e "
                "por data estão em Por Empresa e Calendário.",
            ),
        ]

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── BDRs ────────────────────────────────────────────────────────────────
    def bdrs(self) -> dict[str, Any]:
        """E os BDRs — os proventos dos recibos *34.

        The BDR twin of the Visão Geral: same KPI set, same distribution
        scale — the payout-per-receipt universe (R$ 1,70-6,32) that
        justified the split, visible in the right tail of the chart.
        """
        agenda = _agenda()
        if agenda is None:
            return error_payload("", _ERR)
        _natives, bdrs = _split(agenda)
        if not bdrs:
            return error_payload(
                "", "Sem BDRs na agenda atual — a janela pode estar sem "
                "eventos *34; sincronize a fonte ddm-dividends.")
        summ = _summarize(bdrs)
        b = _bucketize(bdrs)

        # ── KPIs (6) ────────────────────────────────────────────────────────
        biggest = summ.get("biggest") or {}
        kpis: list[dict[str, Any]] = [
            kpi("Total de Proventos BDR", _int(summ["total"]),
                f"Dividendo: {_int(summ['by_tipo']['Dividendo'])} | "
                f"JCP: {_int(summ['by_tipo']['JCP'])}. BDRs = Brazilian "
                "Depositary Receipts — ações de empresas estrangeiras "
                "negociadas na B3 (tickers terminados em 34)."),
            kpi("Empresas Pagadoras (BDR)", _int(summ["tickers"]),
                "Recibos *34 distintos com evento na agenda — cada BDR "
                "é uma empresa estrangeira."),
            kpi("Valor Total (BDR)", _brl(summ["total_value"]),
                "Soma dos valores por recibo — pagamentos em R$ de "
                "empresas estrangeiras via B3."),
        ]
        if biggest.get("ticker"):
            kpis.append(kpi(
                "Maior Provento (BDR)", _brl(biggest["value"]),
                f"{biggest['ticker']} ({biggest['tipo']}) — pagamento em "
                f"{_fmt_data(biggest.get('payment_date', ''))}."))
        if summ["median_value"] is not None:
            kpis.append(kpi(
                "Valor Mediano (BDR)", _brl(summ["median_value"]),
                "Metade dos eventos BDR paga menos que isso (média: "
                f"{_brl(summ['mean_value'])})."))
        if summ["next_payment_date"]:
            kpis.append(kpi(
                "Próximo Pagamento (BDR)",
                _fmt_data(summ["next_payment_date"]),
                "A próxima data de pagamento dos BDRs."))

        # ── Sections ────────────────────────────────────────────────────────
        above_1 = sum(b["totals"][5:])
        sections: list[dict[str, Any]] = [
            _distribution_chart(
                "Distribuição por Faixa de Valor — BDRs",
                bdrs,
                "A mesma escala de 8 faixas, agora só com os BDRs — os "
                "pagamentos por recibo vivem num universo de valor "
                "próprio: a distribuição estica para a direita ("
                f"{_plain_pct(100.0 * above_1 / summ['total']) if summ['total'] else '-'} "
                "acima de R$ 1,00) enquanto a das ações B3 se concentra "
                "abaixo disso. É por isso que a Visão Geral os separa."),
            _agenda_table(
                "Agenda de Proventos — BDRs",
                bdrs,
                f"Os {_int(len(bdrs))} proventos dos BDRs; o ⓘ do código "
                "explica o recibo. Mesmo contrato da tabela B3: "
                "ordenável, padrão Valor DESC.",
                "BDRs pagam em R$ na B3, mas o valor por recibo reflete "
                "o dividendo da ação estrangeira — não comparável "
                "direto com o por ação das empresas brasileiras.",
            ),
        ]

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Por Empresa ─────────────────────────────────────────────────────────
    def empresas(self) -> dict[str, Any]:
        """Quem paga — a agenda agregada por empresa.

        The aggregation the flat table hid: per-ticker event count,
        summed/avg/max value, last payment — with the BDR class visible
        (the top of the value ranking is BDR-dominated; that's the
        insight the Top 10 chart shows in color).
        """
        agenda = _agenda()
        if agenda is None:
            return error_payload("", _ERR)
        empresas = _by_empresa(agenda)
        if not empresas:
            return error_payload("", _ERR)

        by_value = empresas                     # already total_value DESC
        by_events = sorted(empresas,
                           key=lambda e: -e["events"])
        n_events = sum(e["events"] for e in empresas)
        n_bdr_events = sum(e["events"] for e in empresas if e["is_bdr"])
        biggest_single = max(
            (e for e in empresas if e["max_event"]),
            key=lambda e: e["max_event"]["value"], default=None)

        # ── KPIs (5) ────────────────────────────────────────────────────────
        kpis: list[dict[str, Any]] = [
            kpi("Maior Pagadora", by_value[0]["ticker"],
                f"{_brl(by_value[0]['total_value'])} somados em "
                f"{by_value[0]['events']} "
                f"evento{'s' if by_value[0]['events'] != 1 else ''}."),
            kpi("Mais Eventos", by_events[0]["ticker"],
                f"{_int(by_events[0]['events'])} eventos na agenda — a "
                "atividade recorrente."),
        ]
        if biggest_single and biggest_single["max_event"]:
            me = biggest_single["max_event"]
            kpis.append(kpi(
                "Maior Provento Individual",
                _brl(me["value"]),
                f"{biggest_single['ticker']} ({me['tipo']}) — pagamento "
                f"em {_fmt_data(me.get('payment_date', ''))}."))
        kpis.append(kpi(
            "Média de Eventos",
            f"{(n_events / len(empresas)):.1f}".replace(".", ","),
            f"{_int(n_events)} eventos ÷ {_int(len(empresas))} "
            "pagadoras da agenda."))
        kpis.append(kpi(
            "Eventos BDR",
            _plain_pct(100.0 * n_bdr_events / n_events) if n_events else "-",
            f"{_int(n_bdr_events)} de {_int(n_events)} eventos vêm de "
            "BDRs — o detalhe está na subaba BDRs."))

        # ── Sections ────────────────────────────────────────────────────────
        sections: list[dict[str, Any]] = [
            _top_empresas_chart(
                "Top 10 Empresas — Valor Total",
                empresas, "value",
                "As 10 maiores pagadoras por valor somado — cada barra "
                "na cor da sua classe (B3 teal, BDR cinza): o topo do "
                "ranking é dominado por BDRs, a leitura que a tabela "
                "única escondia."),
            _top_empresas_chart(
                "Top 10 Empresas — Nº de Eventos",
                empresas, "events",
                "As 10 empresas com mais eventos na agenda (quem paga "
                "várias vezes no mês), na mesma paleta B3/BDR."),
        ]

        rows: list[list[Any]] = []
        for e in empresas:
            me = e.get("max_event") or {}
            rows.append([
                {"text": e["ticker"],
                 "tooltip": ("BDR — Brazilian Depositary Receipt "
                             "(empresa estrangeira negociada na B3)."
                             if e["is_bdr"] else
                             "Ação listada na B3 (nativa).")},
                "BDR" if e["is_bdr"] else "B3",
                _int(e["events"]),
                _brl(e["total_value"]),
                _brl(e["avg_value"]),
                _brl(me.get("value")),
                _fmt_data(e["last_payment"]) or "—",
            ])
        tbl = table_section(
            "Todas as Empresas",
            ["Empresa", "Classe", "Eventos", "Valor Total (R$)",
             "Média (R$)", "Máximo (R$)", "Último Pagamento"],
            rows,
            description=(
                f"A agenda agregada por empresa: {_int(len(empresas))} "
                "pagadoras — eventos, valor total, média, máximo e o "
                "último pagamento (padrão: Valor Total DESC; o ⓘ da "
                "empresa explica a classe)."
            ),
            note=(
                "A coluna Tipo por evento (Dividendo/JCP) está na "
                "agenda completa — Visão Geral e BDRs."
            ),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Calendário ──────────────────────────────────────────────────────────
    def calendario(self) -> dict[str, Any]:
        """Quando cai — os pagamentos por data.

        The time dimension: one row per payment date (pago vs a pagar
        against today), with the day's main payers. The agenda is a
        rolling window — each sync brings the current month.
        """
        agenda = _agenda()
        if agenda is None:
            return error_payload("", _ERR)
        days = _by_day(agenda)
        if not days:
            return error_payload(
                "", "Sem datas de pagamento na agenda — sincronize a "
                "fonte ddm-dividends.")

        today = _dt.now().strftime("%Y-%m-%d")
        upcoming = [d for d in days if d["date"] >= today]
        paid = [d for d in days if d["date"] < today]
        busiest = max(days, key=lambda d: d["events"])
        next_day = upcoming[0] if upcoming else days[-1]

        # ── KPIs (4) ────────────────────────────────────────────────────────
        kpis: list[dict[str, Any]] = [
            kpi("Próximo Pagamento", _fmt_data(next_day["date"]),
                f"{_int(next_day['events'])} evento"
                f"{'s' if next_day['events'] != 1 else ''} · "
                f"{_brl(next_day['value'])} no dia."),
            kpi("A Pagar",
                _int(sum(d["events"] for d in upcoming)),
                f"{_brl(sum(d['value'] for d in upcoming))} em "
                f"{_int(len(upcoming))} data"
                f"{'s' if len(upcoming) != 1 else ''} a partir de "
                f"{_fmt_data(today)}."),
            kpi("Já Pago",
                _int(sum(d["events"] for d in paid)),
                f"{_brl(sum(d['value'] for d in paid))} em "
                f"{_int(len(paid))} data"
                f"{'s' if len(paid) != 1 else ''} na janela."),
            kpi("Dia com Mais Pagamentos", _fmt_data(busiest["date"]),
                f"{_int(busiest['events'])} eventos · "
                f"{_brl(busiest['value'])} no dia."),
        ]

        # ── Sections ────────────────────────────────────────────────────────
        # ISO labels on purpose — renderValChart formats date axes
        # client-side (the fluxo daily-chart contract).
        labels = [d["date"] for d in days]
        ds_paid = [round(d["value"], 6) if d["date"] < today else None
                   for d in days]
        ds_topay = [round(d["value"], 6) if d["date"] >= today else None
                    for d in days]
        sections: list[dict[str, Any]] = [
            chart_section(
                "Pagamentos por Dia",
                {
                    "type": "bar",
                    "data": {
                        "labels": labels,
                        "datasets": [
                            {"label": "Pago", "data": ds_paid,
                             "backgroundColor": _C_DIV},
                            {"label": "A pagar", "data": ds_topay,
                             "backgroundColor": _C_JCP},
                        ],
                    },
                    "options": {
                        "interaction": {"mode": "index",
                                        "intersect": False},
                        "scales": {
                            "y": {"title": {"display": True,
                                            "text": "Valor (R$)"},
                                  "beginAtZero": True},
                        },
                        "tooltipUnit": " R$",
                    },
                },
                description=(
                    "O valor a pagar por data de pagamento — já pago "
                    "(teal) vs a pagar (âmbar, a partir de hoje). A "
                    "agenda é uma janela móvel: cada sincronização da "
                    "fonte ddm-dividends traz o mês corrente."
                ),
            ),
        ]

        rows: list[list[Any]] = []
        for d in reversed(days):                     # newest first
            payers = " · ".join(
                f"{t} ({_brl(v)})" for t, v in d["payers"])
            tip = " · ".join(f"{t}: {_brl(v)}" for t, v in d["payers"])
            rows.append([
                {"text": _fmt_data(d["date"]),
                 "tooltip": f"Maiores pagadores do dia: {tip}."},
                _int(d["events"]),
                _int(d["bdr_events"]),
                _brl(d["value"]),
                _brl(d["bdr_value"]),
                payers or "—",
            ])
        tbl = table_section(
            "Calendário de Pagamentos",
            ["Data", "Eventos", "BDRs", "Valor Total (R$)",
             "Valor BDR (R$)", "Principais Pagadores"],
            rows,
            description=(
                "Um dia por linha: eventos, quantos são BDRs, o valor "
                "total e os principais pagadores (o ⓘ da data carrega o "
                "top-3 do dia). Mais recentes primeiro; clique no "
                "cabeçalho para ordenar."
            ),
            note=(
                "A janela cobre o mês corrente da agenda — datas sem "
                "evento não aparecem (a soma dos dias é o total da "
                "janela, não do ano)."
            ),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}
