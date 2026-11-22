"""webui/services/fluxo.py — Mercado page / Fluxo family data service (DDM).

[v1.13] The Fluxo family of the ``/webui/mercado`` page — a reorganized
take on the static ``fluxo_dashboard.html`` reference (built by
skills/ddm/fluxo/modes/dashboard.py, 5 flat tabs: 1 Fluxo overview + 4
per-investor tabs each with Diário/Mensal/Anual subtabs). Second family
of the Mercado page (focus was v1.12) — the B3 investment flow by
investor type, also from dadosdemercado.com.br.

Per the v1.8–v1.12 reorganization spirit the static's parallel
per-investor navigation collapses into comparison views (the static's
gap: monthly/annual cross-investor comparison required flipping 4 tabs
and memorizing) and its gaps get fixed, not copied:

  overview       → "onde o dinheiro está entrando?"   (6 KPIs + o fluxo
                    diário de TODOS os investidores num único chart de
                    colunas EMPILHADAS (v1.13 fix1 — o estático desenhava
                    colunas lado a lado; empilhado, a altura líquida de
                    cada coluna é o total do pregão) + a tabela diária
                    completa)
  mensal         → "como fechou cada mês?"            (acumulado mensal
                    COMPARADO — chart + tabela Mês × investidor + Total;
                    o estático tinha 4 tabelas separadas)
  anual          → "como está o ano?"                 (acumulado YTD
                    corrente por investidor — a serra dente-de-serra
                    que reseta em 1º de janeiro + totais por ano)
  por_investidor → "o que cada tipo fez?"             (o chart diário
                    verde/vermelho por sinal de CADA investidor — os 4
                    do estático consolidados + Outros, que o estático
                    só mostrava como coluna da tabela diária)

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker — the
B3 flow is market-wide. The adapters registry dispatches these through
the v1.11 ticker-less path and the generic endpoint
``GET /api/webui/mercado/sections/{key}`` serves them; all subtabs
render through the generic renderer (loadFluxoSubtab → valKpisHtml +
valSectionsHtml + mountValCharts in app.js).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.fluxo.query_engine`` (memory_db/ddm/fluxo.db —
    daily net flow per investor type, ~1 year window)

Formatting = the skill's helpers (``skills/ddm/fluxo/helpers.py`` —
``format_brl`` table cells full precision "R$ -1.582,35 mi",
``format_brl_from_millions`` KPI auto-scale "R$ 30,16 bi"). No forked
numerics.

Improvements over the static dashboard:
  - The 4 per-investor tabs' monthly/annual views become COMPARISON
    views (one chart + one Mês × investidor table) — the static could
    not answer "quem comprou mais em outubro?" without flipping tabs.
  - "Outros" joins every view (table columns, comparison charts, its own
    sign-colored daily chart) — the static kept it a bare daily-table
    column.
  - The static's 10 KPI cards (Líquido anual + Líquido 365d × 4) become
    6: the 365d number rides the YTD card's tooltip (v1.10 tooltip
    pattern).
  - The static's "Tabela acumulada" (244 daily running rows) becomes a
    year-totals table — the running line already carries the daily
    detail.
  - Degradation: missing fluxo.db → PT-BR ``_error`` naming the
    ``ddm-fluxo`` source exactly as the Sincronização page lists it.

Data conventions (v1.8 fix1 / v1.9–v1.12 lineage):
  - Table dates dd/mm/yyyy; months "nov/2026" (sortable — _valSortKey
    parses that form). Chart labels ship ISO on purpose — renderValChart
    formats ticks + tooltips client-side (daily + YTD charts).
  - Every number is a PRE-FORMATTED PT-BR string — the client only
    colorizes (negative red).
"""
from __future__ import annotations

from datetime import timedelta as _td
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
from data_sources.ddm.fluxo.query_engine import (
    fluxo_data as _fluxo_data,
    summary as _summary,
)

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.ddm.fluxo.helpers import (
    format_brl as _fmt_mi,              # "R$ -1.582,35 mi" (table cells)
    format_brl_from_millions as _fmt_big,  # "R$ 30,16 bi" (KPIs/totals)
)

# ── investor columns: DB column, PT-BR label, chart color (static palette) ──
_INVESTORS = [
    ("estrangeiro",     "Estrangeiro",     "#3b82f6"),  # blue
    ("institucional",   "Institucional",   "#ef4444"),  # red
    ("pessoa_fisica",   "Pessoa física",   "#f59e0b"),  # amber
    ("inst_financeira", "Inst. Financeira", "#22c55e"),  # green
    ("outros",          "Outros",          "#8b5cf6"),  # violet
]

# The 4 the static elevates to KPI cards ("outros" stays a residual —
# table/chart only, same call the skill makes).
_KPI_INVESTORS = [i for i in _INVESTORS if i[0] != "outros"]

_C_POS = "#22c55e"   # green — positive day (buy)
_C_NEG = "#ef4444"   # red   — negative day (sell)

_BR_MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez")


# ── helpers ─────────────────────────────────────────────────────────────────
def _fmt_date(s: Any) -> Any:
    """ISO YYYY-MM-DD → dd/mm/yyyy (v1.8 fix1 convention; passthrough)."""
    if isinstance(s, str) and len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _br_month(ym: Any) -> Any:
    """'2026-11' → 'nov/2026' (short PT-BR month, sortable by _valSortKey)."""
    if isinstance(ym, str) and len(ym) == 7 and ym[4] == "-":
        m = int(ym[5:7])
        if 1 <= m <= 12:
            return f"{_BR_MONTHS[m - 1]}/{ym[0:4]}"
    return ym


def _snapshot() -> dict[str, Any]:
    """fluxo_data() + summary() merged; ``_error`` payload on any failure.

    One snapshot serves every subtab (the flow is ~244 daily rows — the
    static dashboard itself slices a single fluxo_data() call in memory).
    """
    data = _fluxo_data()
    if data.get("status") != "ok":
        return {"_error": (
            "Fluxo de investimento indisponível — sincronize a fonte "
            "ddm-fluxo (DDM — fluxo de investidores, dadosdemercado."
            "com.br) na página Sincronização.")}
    obs: list[dict[str, Any]] = data.get("observations", [])
    if not obs:
        return {"_error": (
            "Fluxo de investimento vazio — a fonte ddm-fluxo sincronizou "
            "sem observações. Rode a sincronização novamente na página "
            "Sincronização.")}
    summ = _summary()
    return {
        "observations": obs,
        "last_date": summ.get("last_date") or obs[-1].get("ref_date", ""),
        "first_date": summ.get("first_date") or obs[0].get("ref_date", ""),
        "row_count": summ.get("row_count") or len(obs),
    }


def _sum(obs: list[dict[str, Any]], field: str,
         predicate=None) -> float | None:
    """Sum one investor column over the rows matching predicate (None-safe)."""
    total, seen = 0.0, False
    for o in obs:
        v = o.get(field)
        if v is None:
            continue
        if predicate is not None and not predicate(o):
            continue
        total += v
        seen = True
    return total if seen else None


def _line_ds(label: str, data: list[Any], color: str) -> dict[str, Any]:
    """One line dataset (server styling is honored by renderValChart)."""
    return {
        "label": label, "data": data,
        "borderColor": color, "backgroundColor": color,
        "borderWidth": 2, "pointRadius": 0,
        "pointHoverRadius": 4, "tension": 0.25, "fill": False,
    }


def _range_chart(title: str, datasets: list[dict[str, Any]],
                 labels: list[str], y_title: str = "R$ mi",
                 description: str = "", chart_type: str = "bar",
                 stacked: bool = False) -> dict:
    """Chart over ISO date labels + the client-side range bar (v1.7.2).

    [v1.13 fix1] ``stacked=True`` ships ``x/y.stacked`` — one column
    per day, one segment per investor (Chart.js stacks the positives
    above zero and the negatives below, so the column's net height is
    the day's total). renderValChart has honored server stacked flags
    since v1.6 fix1 — no client change needed.
    """
    y_scale: dict[str, Any] = {"title": {"display": True, "text": y_title}}
    if stacked:
        y_scale["stacked"] = True
    scales: dict[str, Any] = {"y": y_scale}
    if stacked:
        scales["x"] = {"stacked": True}
    cd: dict[str, Any] = {
        "type": chart_type,
        "data": {"labels": labels, "datasets": datasets},
        "options": {"scales": scales},
    }
    sec = chart_section(title, cd, description=description)
    sec["price_range_selector"] = True   # client-side range bar
    return sec


# ── service ─────────────────────────────────────────────────────────────────
class FluxoService:
    """Mercado page / Fluxo family — 4 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """Onde o dinheiro está entrando — KPIs + fluxo diário + tabela.

        Landing subtab (the static's Fluxo tab): the GENERAL view — every
        investor in ONE stacked-column chart (v1.13 fix1: one column per
        pregão, one segment per investor — the net column height is the
        day's total) + the complete daily table. The specific
        per-investor views live in their own subtabs.
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        obs = snap["observations"]
        last = snap["last_date"]
        year = last[:4] if last else ""

        # 365d cutoff (the static's rolling window — last_date − 365d).
        try:
            cutoff = (_dt.strptime(last, "%Y-%m-%d") - _td(days=365)
                      ).strftime("%Y-%m-%d") if last else ""
        except ValueError:
            cutoff = ""

        kpis: list[dict[str, Any]] = [
            kpi("Última data", _fmt_date(last) or "-",
                "Dia de negociação mais recente sincronizado na fonte "
                "ddm-fluxo."),
            kpi("Dias na base", str(snap["row_count"]),
                f"Janela sincronizada: {_fmt_date(snap['first_date'])} a "
                f"{_fmt_date(last)} (dias de negociação)."),
        ]
        for field, label, _c in _KPI_INVESTORS:
            ytd = _sum(obs, field, lambda o: o["ref_date"].startswith(year)) \
                if year else None
            d365 = _sum(obs, field, lambda o: o["ref_date"] >= cutoff) \
                if cutoff else None
            kpis.append(kpi(
                f"{label} — ano",
                _fmt_big(ytd),
                f"Saldo líquido no ano ({year}): entrada − saída. "
                f"Últimos 365 dias: {_fmt_big(d365)}. Valores em milhões "
                "de R$ (formato compacto).",
            ))

        labels = [o["ref_date"] for o in obs]
        datasets = [
            {"label": label, "data": [o.get(f) for o in obs],
             "backgroundColor": color}
            for f, label, color in _INVESTORS
        ]
        sections = [
            _range_chart(
                "Fluxo diário por investidor",
                datasets, labels,
                stacked=True,
                description=(
                    "Fluxo diário de investimento na B3 por tipo de "
                    "investidor (em milhões de R$), em colunas "
                    "EMPILHADAS: cada pregão é uma coluna e cada "
                    "segmento, um tipo — Estrangeiro (azul), "
                    "Institucional (vermelho), Pessoa física (amarelo), "
                    "Inst. Financeira (verde), Outros (violeta). "
                    "Segmentos positivos empilham acima do zero "
                    "(compra) e negativos abaixo (venda) — a altura "
                    "líquida da coluna é o fluxo total do dia. Use a "
                    "barra de período para filtrar."
                ),
            ),
        ]

        # Complete daily table — newest first (static convention), sortable.
        rows = []
        for o in reversed(obs):
            total = sum(v for v in (o.get(f) for f, _l, _c in _INVESTORS)
                        if v is not None)
            rows.append([
                _fmt_date(o["ref_date"]),
                *[_fmt_mi(o.get(f)) for f, _l, _c in _INVESTORS],
                _fmt_mi(total if total != 0 else None),
            ])
        tbl = table_section(
            "Tabela diária completa",
            ["Data", "Estrangeiro", "Institucional", "Pessoa física",
             "Inst. Financeira", "Outros", "Total"],
            rows,
            description=(
                "Todas as observações diárias (mais recentes primeiro). "
                "Valores em milhões de R$. Clique no cabeçalho para "
                "ordenar — a coluna Data ordena cronologicamente."
            ),
            note=(f"{snap['row_count']} dias sincronizados — o acumulado "
                  "por mês e por ano está nas subabas Mensal e Anual; o "
                  "recorte de cada tipo de investidor, em Por Investidor."),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Mensal ──────────────────────────────────────────────────────────────
    def mensal(self) -> dict[str, Any]:
        """Como fechou cada mês — acumulado mensal comparado.

        The static's 4 per-investor monthly tables become ONE Mês ×
        investidor comparison (its gap: "quem comprou mais em outubro?"
        required flipping tabs).
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        obs = snap["observations"]

        # Month buckets, ASC (one pass over the daily rows).
        months: dict[str, dict[str, float]] = {}
        for o in obs:
            ym = o["ref_date"][:7]
            bucket = months.setdefault(
                ym, {f: 0.0 for f, _l, _c in _INVESTORS})
            for f, _l, _c in _INVESTORS:
                v = o.get(f)
                if v is not None:
                    bucket[f] += v
        ym_list = sorted(months)

        labels = [_br_month(ym) for ym in ym_list]
        datasets = [
            _line_ds(label, [round(months[ym][f], 2) for ym in ym_list],
                     color)
            for f, label, color in _INVESTORS
        ]
        totals = [sum(months[ym].values()) for ym in ym_list]

        # Best/worst month KPIs (by the total net flow).
        kpis: list[dict[str, Any]] = []
        if ym_list:
            best_i = max(range(len(ym_list)), key=lambda i: totals[i])
            worst_i = min(range(len(ym_list)), key=lambda i: totals[i])
            kpis.append(kpi(
                "Mês mais comprador", _br_month(ym_list[best_i]),
                f"Fluxo líquido total de TODOS os investidores: "
                f"{_fmt_big(totals[best_i])}."))
            kpis.append(kpi(
                "Mês mais vendedor", _br_month(ym_list[worst_i]),
                f"Fluxo líquido total de TODOS os investidores: "
                f"{_fmt_big(totals[worst_i])}."))
            kpis.append(kpi(
                "Meses na base", str(len(ym_list)),
                f"{_br_month(ym_list[0])} a {_br_month(ym_list[-1])} "
                "(meses com pelo menos um pregão sincronizado)."))

        rows = []
        for ym in reversed(ym_list):   # newest first
            tot = sum(months[ym].values())
            rows.append([
                _br_month(ym),
                *[_fmt_mi(round(months[ym][f], 2)) for f, _l, _c in _INVESTORS],
                _fmt_mi(round(tot, 2)),
            ])

        tbl = table_section(
            "Acumulado mensal por investidor",
            ["Mês", "Estrangeiro", "Institucional", "Pessoa física",
             "Inst. Financeira", "Outros", "Total"],
            rows,
            description=(
                "Saldo líquido de cada mês (soma dos fluxos diários), "
                "todos os tipos de investidor lado a lado — mais recentes "
                "primeiro. Valores em milhões de R$."
            ),
            note=("A coluna Total é a soma líquida dos cinco tipos — "
                  "meses positivos são de compra líquida do mercado."),
        )
        tbl["sortable"] = True

        return {
            "status": "ok",
            "kpis": kpis,
            "sections": [
                chart_section(
                    "Acumulado mensal — todos os investidores",
                    {
                        "type": "line",
                        "data": {"labels": labels, "datasets": datasets},
                        "options": {"scales": {"y": {"title": {
                            "display": True, "text": "R$ mi"}}}},
                    },
                    description=(
                        "Saldo líquido mensal por tipo de investidor "
                        "(linha por tipo). O estático exigia alternar "
                        "entre 4 abas para comparar os mesmos meses."
                    ),
                ),
                tbl,
            ],
        }

    # ── Anual ───────────────────────────────────────────────────────────────
    def anual(self) -> dict[str, Any]:
        """Como está o ano — acumulado YTD corrente por investidor.

        The running cumulative resets on January 1st (sawtooth) — the
        query engine's annual_cumulative semantics ([v2 fix B9]: YTD, not
        since-inception). Chart = the running lines; table = the year
        TOTALS (the static's 244-row running table is redundant with the
        chart).
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        obs = snap["observations"]

        # Running YTD per investor (one pass; resets on year boundary).
        labels: list[str] = []
        running = {f: [] for f, _l, _c in _INVESTORS}
        state = {f: 0.0 for f, _l, _c in _INVESTORS}
        current_year = ""
        for o in obs:
            y = o["ref_date"][:4]
            if y != current_year:
                current_year = y
                state = {f: 0.0 for f, _l, _c in _INVESTORS}
            labels.append(o["ref_date"])
            for f, _l, _c in _INVESTORS:
                v = o.get(f)
                if v is not None:
                    state[f] += v
                running[f].append(round(state[f], 2))

        datasets = [
            _line_ds(label, running[f], color)
            for f, label, color in _INVESTORS
        ]

        # Year totals (the last running value of each year = the YTD sum).
        year_tot: dict[str, dict[str, float]] = {}
        for o in obs:
            y = o["ref_date"][:4]
            bucket = year_tot.setdefault(
                y, {f: 0.0 for f, _l, _c in _INVESTORS})
            for f, _l, _c in _INVESTORS:
                v = o.get(f)
                if v is not None:
                    bucket[f] += v

        rows = []
        for y in sorted(year_tot, reverse=True):
            tot = sum(year_tot[y].values())
            rows.append([
                y,
                *[_fmt_mi(round(year_tot[y][f], 2))
                  for f, _l, _c in _INVESTORS],
                _fmt_mi(round(tot, 2)),
            ])
        tbl = table_section(
            "Totais por ano",
            ["Ano", "Estrangeiro", "Institucional", "Pessoa física",
             "Inst. Financeira", "Outros", "Total"],
            rows,
            description=(
                "Saldo líquido por ano calendário (o ano corrente é "
                "year-to-date — acumula até a última data sincronizada). "
                "Valores em milhões de R$."
            ),
        )
        tbl["sortable"] = True

        return {
            "status": "ok",
            "sections": [
                _range_chart(
                    "Acumulado no ano (YTD) por investidor",
                    datasets, labels,
                    description=(
                        "Saldo líquido acumulado desde 1º de janeiro — a "
                        "linha reseta a cada ano (dente-de-serra). Cada "
                        "cor é um tipo de investidor; a inclinação de cada "
                        "trecho é o ritmo diário de compra/venda."
                    ),
                    chart_type="line",
                ),
                tbl,
            ],
        }

    # ── Por Investidor ──────────────────────────────────────────────────────
    def por_investidor(self) -> dict[str, Any]:
        """O que cada tipo fez — fluxo diário verde/vermelho por sinal.

        The static's 4 per-investor daily charts consolidated (+ Outros,
        new). Sign coloring (green buy / red sell) per bar — in the
        comparison chart the colors distinguish investors, here they
        distinguish direction.
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        obs = snap["observations"]
        labels = [o["ref_date"] for o in obs]

        sections = []
        for f, label, color in _INVESTORS:
            data = [o.get(f) for o in obs]
            bar_colors = [_C_POS if (v is not None and v >= 0) else _C_NEG
                          for v in data]
            ytd = _sum(obs, f)
            sections.append(_range_chart(
                f"{label} — fluxo diário",
                [{"label": label, "data": data,
                  "backgroundColor": bar_colors}],
                labels,
                description=(
                    f"Fluxo diário de {label} (milhões de R$): verde = "
                    f"entrada (compra), vermelho = saída (venda). "
                    f"Saldo no período sincronizado: {_fmt_big(ytd)}."
                ),
            ))

        return {"status": "ok", "sections": sections}
