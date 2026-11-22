"""webui/services/acoes.py — Mercado page / Ações family data service (DDM).

[v1.17] The Ações family of the ``/webui/mercado`` page — a reorganized
take on the static ``acoes_dashboard.html`` reference (built by
skills/ddm/acoes/modes/dashboard.py: 1 flat tab — 4 KPIs + the 22-range
price-distribution bar chart + the sortable stocks table). Sixth family
of the Mercado page (focus v1.12, fluxo v1.13, índices v1.14, inflação
v1.15, juros v1.16) — the B3 listed stocks scraped from
dadosdemercado.com.br/acoes (~370 tickers: Ticker | Nome | Negócios |
Última (R$) | Variação).

The headline of v1.17 is the EVOLUTION: the /acoes page is a LIVE quote
table with no history, so the data source now ACCUMULATES one snapshot
per sync in ``stocks_history`` (v2 of the sync engine — the first sync
after the upgrade also preserves the previous ``stocks`` snapshot). The
Evolução subtab charts the price distribution OVER TIME from those
snapshots — the 100% stacked area (each band a price range in the
shared palette's color, bands summing to exactly 100% on every date) +
the absolute counts — the reference-chart style for distribution
monitoring.

Per the v1.8–v1.16 reorganization spirit the static's gaps get fixed,
not copied:

  overview → "onde estão os preços?"            (os 4 KPIs do estático
              + 2 novos que a distribuição pede — Faixa Mais Comum e
              Preço Mediano; a distribuição de preços em barras (as 22
              faixas da paleta) + o Top 10 Mais Negociadas — quem
              domina o pregão, inédito — + a tabela completa ordenável)
  evolucao → "como a distribuição se move?"     (inédita: o estático
              só conhecia o dia corrente. A área 100% empilhada — um
              ponto por snapshot diário — + a visão absoluta + a tabela
              por data com bandas agrupadas; <2 snapshots degradam em
              nota explicando o acúmulo — o caso vazio cai no snapshot
              atual, que é exatamente o que o próximo sync preserva)

Improvements over the static dashboard:
  - The evolution itself (the static had NO time dimension — the page
    carries no history; v1.17 stores it).
  - The Top 10 Mais Negociadas chart is NEW (the static answered "quem
    domina o volume?" only by scrolling its table).
  - The overview KPI set grows from 4 to 6 with Faixa Mais Comum and
    Preço Mediano (the two single-glance reads of the distribution).
  - The evolução table groups the 22 ranges into 5 readable bands
    (< R$ 5 / 5–15 / 15–50 / 50–100 / ≥ 100) — the 22-range detail
    lives in the charts; the ⓘ of each date carries its top-3 faixas.
  - Skill-side fixes shipped together (skill v2): PT-BR accents in
    every user-facing string ("Ações", "Negócios", "Distribuição de
    Preços"… — the juros/inflation statics always had them), the stale
    "16 colored bars" → 22 ranges, and the evolution sections in the
    static dashboard itself.

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker — the
listed universe is market-wide. The adapters registry dispatches these
through the v1.11 ticker-less path and the generic endpoint
``GET /api/webui/mercado/sections/{key}`` serves them; all subtabs
render through the generic renderer (loadAcoesSubtab → valKpisHtml +
valSectionsHtml + mountValCharts in app.js).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.acoes.query_engine`` (memory_db/ddm/acoes.db —
    stocks: ~370 rows, the current snapshot; stocks_history: the
    evolution store, one snapshot per sync day since the v2 schema)

Numerics = the skill's shared helpers (``skills/ddm/acoes/helpers.py``):
  ``distribution_snapshots`` buckets every snapshot into the shared
  22-range palette (counts + shares that sum to EXACTLY 100 per date)
  — the same function the static dashboard uses; ``format_brl`` /
  ``format_int`` / ``format_pct`` / ``_format_data`` for the PT-BR
  display strings. No forked numerics.

Data conventions (v1.8 fix1 / v1.9–v1.16 lineage):
  - Table dates dd/mm/yyyy (sortable — _valSortKey parses that form);
    chart labels ship ISO "YYYY-MM-DD" on purpose — renderValChart
    formats date axes + tooltips client-side and valChartRange slices
    the ISO strings lexicographically (the fluxo daily-chart contract).
  - Every number is a PRE-FORMATTED PT-BR string — the client only
    colorizes (negative red, % green).
  - The 22-band charts ship ``interaction: {mode: 'nearest'}`` (honored
    client-side since v1.17) — an index tooltip would be a wall of 22
    rows; the table below carries the full per-date breakdown.
  - Degradation: missing/empty acoes.db → PT-BR ``_error`` naming the
    ``ddm-acoes`` source exactly as the Sincronização page lists it
    (DDM — ações B3).
"""
from __future__ import annotations

from datetime import date as _date
from statistics import mean, median
from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    kpi,
    table_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.ddm.acoes.query_engine import (
    stocks_list as _stocks_list,
    price_history as _price_history,
)

# ── the skill's display + numerics helpers (no forked numerics) ─────────────
from skills._colors.price import price_range_color
from skills.ddm.acoes.helpers import (
    format_brl as _brl,             # "R$ 44,30" / "-" for None
    format_int as _int,             # "52.792.400"
    format_pct as _pct,             # "+2,78%" / "-10,85%"
    distribution_snapshots as _snapshots,
    _format_data as _fmt_data,      # "2026-11-15" → "15/11/2026"
)

_ERR = ("Cotações das ações B3 indisponíveis — sincronize a fonte "
        "ddm-acoes (DDM — ações B3, dadosdemercado.com.br) na página "
        "Sincronização.")

# The 22 palette ranges grouped into 5 readable bands for the evolução
# table (boundaries align with the palette's own: <5 | 5–15 | 15–50 |
# 50–100 | ≥100). Index ranges over the palette order (lowest first).
_GROUPS: list[tuple[str, range]] = [
    ("< R$ 5",   range(0, 3)),
    ("R$ 5–15",  range(3, 5)),
    ("R$ 15–50", range(5, 10)),
    ("R$ 50–100", range(10, 15)),
    ("≥ R$ 100", range(15, 22)),
]


# ── helpers ─────────────────────────────────────────────────────────────────
def _compact(label: str) -> str:
    """'2 ≤ X < 5' → '2–5' (the 22 palette labels, compact axis form)."""
    return (label.replace(" ≤ X < ", "–")
                 .replace("X < ", "< ")
                 .replace("X ≥ ", "≥ "))


def _plain_pct(v: float, decimals: int = 1) -> str:
    """22.58 → '22,6%' (unsigned, PT-BR comma — table/KPI shares)."""
    return f"{v:.{decimals}f}".replace(".", ",") + "%"


def _pp(v: float) -> str:
    """3.21 → '+3,2 p.p.' (signed percentage-point delta)."""
    return f"{v:+.1f}".replace(".", ",") + " p.p."


def _stocks() -> list[dict[str, Any]] | None:
    """Current snapshot sorted Negócios DESC; None on any failure."""
    try:
        res = _stocks_list(order_by="negocios", direction="desc")
    except Exception:
        return None
    if res.get("status") != "ok":
        return None
    stocks = res.get("stocks") or []
    return stocks or None


def _area_datasets(snap: dict[str, Any], series: list[list[Any]],
                   ) -> list[dict[str, Any]]:
    """One filled dataset per price range, lowest prices at the bottom.

    ``series`` is [date][range] (the distribution_snapshots shape);
    Chart.js needs [range][date] — transposed here. Chart.js stacks
    dataset 0 at the BOTTOM, so the palette order (lowest range first)
    puts the red/pink low-price bands at the bottom, the reference
    chart's layout.
    """
    by_range = [
        [day[r] for day in series] for r in range(len(snap["ranges"]))
    ]
    return [
        {
            "label":           _compact(rng["label"]),
            "data":            row,
            "backgroundColor": rng["color"],
            "borderColor":     rng["color"],
            "borderWidth":     0,
            "fill":            True,
            "pointRadius":     0,
            "tension":         0.2,
        }
        for rng, row in zip(snap["ranges"], by_range)
    ]


def _evolution_chart(title: str, datasets: list[dict[str, Any]],
                     dates: list[str], y_title: str, tooltip_unit: str,
                     description: str, y_max: float | None = None,
                     ) -> dict[str, Any]:
    """One stacked-area evolution chart (the v1.17 webui shape)."""
    y_scale: dict[str, Any] = {
        "stacked": True,
        "title": {"display": True, "text": y_title},
    }
    # The 100% chart pins the axis at 100 — the shares sum to EXACTLY
    # 100.00 per date server-side, but the client's float addition
    # (8.87 + 9.14 + …) can dust past 100 and auto-nice the axis to 120.
    if y_max is not None:
        y_scale["max"] = y_max
    cd: dict[str, Any] = {
        "type": "line",
        "data": {"labels": list(dates), "datasets": datasets},
        "options": {
            "interaction": {"mode": "nearest", "intersect": False},
            "scales": {
                "x": {"stacked": True},
                "y": y_scale,
            },
            "plugins": {
                "legend": {"display": True, "position": "bottom"},
            },
            "tooltipUnit": tooltip_unit,
        },
    }
    sec = chart_section(title, cd, description=description)
    sec["price_range_selector"] = True   # client-side range bar
    return sec


def _grouped_shares(shares_row: list[float]) -> list[float]:
    """Sum the 22 range shares into the 5 table bands (still ~100)."""
    return [round(sum(shares_row[i] for i in idx), 1)
            for _name, idx in _GROUPS]


def _top3_ranges(counts_row: list[int], ranges: list[dict[str, Any]],
                 total: int) -> str:
    """The 3 most populated ranges of one date — the Data cell tooltip."""
    top = sorted(range(len(counts_row)), key=lambda i: -counts_row[i])[:3]
    parts = [
        f"{ranges[i]['label']}: {_int(counts_row[i])} ações "
        f"({_plain_pct(100.0 * counts_row[i] / total) if total else '0%'})"
        for i in top if counts_row[i]
    ]
    return " · ".join(parts)


# ── service ─────────────────────────────────────────────────────────────────
class AcoesService:
    """Mercado page / Ações family — 2 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """Onde estão os preços — o snapshot do universo listado.

        Landing subtab: the static's whole 1-tab content reorganized —
        the KPIs grow from 4 to 6 (Faixa Mais Comum + Preço Mediano,
        the two single-glance reads of the distribution), the
        distribution chart keeps the 22-range palette, and the Top 10
        Mais Negociadas is NEW. The time dimension lives in Evolução.
        """
        stocks = _stocks()
        if stocks is None:
            return error_payload("", _ERR)

        ref_date = stocks[0].get("ref_date", "") or ""
        prices = [s.get("last_price") for s in stocks]
        valid = [p for p in prices if p is not None]
        snap = _snapshots([ref_date or "hoje"], [prices])
        counts_row = snap["counts"][0] if snap["counts"] else []
        total_priced = snap["totals"][0] if snap["totals"] else 0

        # ── KPIs (6) ────────────────────────────────────────────────────────
        kpis: list[dict[str, Any]] = [
            kpi("Total de Ações", _int(len(stocks)),
                "Ações B3 listadas na página /acoes do "
                "dadosdemercado.com.br"
                + (f" · snapshot de {_fmt_data(ref_date)}." if ref_date
                   else ".")),
        ]

        # Mais negociada / maior alta / maior baixa (the static's trio).
        by_neg = [s for s in stocks if s.get("negocios") is not None]
        if by_neg:
            mt = max(by_neg, key=lambda s: s["negocios"])
            kpis.append(kpi(
                "Mais Negociada", mt.get("ticker", ""),
                f"{mt.get('name', '')} — {_int(mt.get('negocios'))} "
                "negócios no snapshot."))
        by_var = [s for s in stocks if s.get("variation") is not None]
        if by_var:
            bg = max(by_var, key=lambda s: s["variation"])
            kpis.append(kpi(
                "Maior Alta", _pct(bg.get("variation")),
                f"{bg.get('ticker', '')} — {bg.get('name', '')}."))
            bl = min(by_var, key=lambda s: s["variation"])
            kpis.append(kpi(
                "Maior Baixa", _pct(bl.get("variation")),
                f"{bl.get('ticker', '')} — {bl.get('name', '')}."))

        # Faixa mais comum + preço mediano (the two NEW reads).
        if counts_row and total_priced:
            top_i = max(range(len(counts_row)), key=lambda i: counts_row[i])
            kpis.append(kpi(
                "Faixa Mais Comum", snap["ranges"][top_i]["label"],
                f"{_int(counts_row[top_i])} ações "
                f"({_plain_pct(100.0 * counts_row[top_i] / total_priced)} "
                "do total) negociadas nesta faixa — a moda da distribuição "
                "de preços."))
        if valid:
            kpis.append(kpi(
                "Preço Mediano", _brl(median(valid)),
                f"Metade das {_int(len(valid))} ações custa menos que "
                f"isso · média: {_brl(mean(valid))}. A mediana é a leitura "
                "de centro que os outliers (as ações de R$ 300+) não "
                "puxam."))

        # ── Sections ────────────────────────────────────────────────────────
        below_50 = sum(counts_row[:10]) if counts_row else 0
        sections: list[dict[str, Any]] = [
            chart_section(
                "Distribuição de Preços",
                {
                    "type": "bar",
                    "data": {
                        "labels": [_compact(r["label"]) for r in snap["ranges"]],
                        "datasets": [{
                            "label": "Número de Ações",
                            "data": counts_row,
                            "backgroundColor": [r["color"] for r in snap["ranges"]],
                        }],
                    },
                    "options": {
                        "scales": {
                            "x": {"title": {"display": True,
                                            "text": "Faixa de preço (R$)"}},
                            "y": {"title": {"display": True,
                                            "text": "Número de ações"},
                                  "beginAtZero": True},
                        },
                        "tooltipUnit": " ações",
                    },
                },
                description=(
                    "A distribuição das ações B3 pelas 22 faixas de preço "
                    "da paleta (vermelho/rosa = preços baixos, amarelo/"
                    "verde = médios, azul = acima de R$ 100) — o mesmo "
                    "gráfico do estático"
                    + (f", snapshot de {_fmt_data(ref_date)}" if ref_date else "")
                    + f". Abaixo de R$ 50: {_plain_pct(100.0 * below_50 / total_priced) if total_priced else '-'}"
                    " das ações."
                ),
            ),
        ]

        # Top 10 mais negociadas — NEW (who dominates the session).
        top10 = [s for s in stocks if s.get("negocios") is not None][:10]
        if top10:
            sections.append(chart_section(
                "Top 10 Mais Negociadas",
                {
                    "type": "bar",
                    "data": {
                        "labels": [s["ticker"] for s in top10],
                        "datasets": [{
                            "label": "Negócios",
                            "data": [s["negocios"] for s in top10],
                            "backgroundColor": [
                                price_range_color(s.get("last_price"))["bg"]
                                for s in top10
                            ],
                        }],
                    },
                    "options": {
                        "scales": {
                            "y": {"title": {"display": True,
                                            "text": "Negócios"},
                                  "beginAtZero": True},
                        },
                        "tooltipUnit": " negócios",
                    },
                },
                description=(
                    "As 10 ações mais negociadas do snapshot, uma barra "
                    "por ticker — cada barra na cor da faixa de preço da "
                    "ação (a mesma paleta da distribuição). O estático "
                    "respondia 'quem domina o pregão?' só rolando a tabela."
                ),
            ))

        # Full sortable table (the static's, dates in PT-BR).
        rows: list[list[Any]] = []
        for s in stocks:
            ticker = s.get("ticker", "")
            faixa = price_range_color(s.get("last_price"))["range"]
            rows.append([
                {"text": ticker, "tooltip": f"Faixa de preço: {faixa}."},
                s.get("name", "") or "—",
                _int(s.get("negocios")),
                _brl(s.get("last_price")),
                _pct(s.get("variation")),
            ])
        tbl = table_section(
            "Ações B3",
            ["Ticker", "Nome", "Negócios", "Última (R$)", "Variação"],
            rows,
            description=(
                f"Todas as {len(rows)} ações listadas (ordem padrão: "
                "Negócios DESC — a pré-ordenação da página). Clique no "
                "cabeçalho para ordenar; o ⓘ do ticker carrega a faixa "
                "de preço da ação."
                + (f" Snapshot de {_fmt_data(ref_date)}." if ref_date else "")
            ),
            note=("A evolução da distribuição de preços ao longo do tempo "
                  "está na subaba Evolução — alimentada pelos snapshots "
                  "que cada sincronização acumula."),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Evolução ───────────────────────────────────────────────────────────
    def evolucao(self) -> dict[str, Any]:
        """Como a distribuição se move — o histórico acumulado dos syncs.

        The v1.17 headline: the /acoes page carries NO history (a live
        quote table), so the data source accumulates one snapshot per
        sync in stocks_history. This subtab charts that evolution — the
        100% stacked area (bands summing to exactly 100% per date) +
        the absolute counts + a per-date table with the 22 ranges
        grouped into 5 bands. Fewer than 2 snapshots degrade to the
        table + a note (the empty case falls back to the CURRENT
        snapshot — exactly what the next sync preserves).
        """
        try:
            hist = _price_history()
        except Exception:
            hist = {"status": "error"}

        dates: list[str] = []
        prices_by_date: list[list] = []
        rows_n = 0
        if hist.get("status") == "ok":
            dates = list(hist.get("dates") or [])
            prices_by_date = list(hist.get("prices") or [])
            rows_n = sum(hist.get("counts") or [])

        # Empty history → fall back to the CURRENT snapshot as the first
        # point (that is exactly what the next sync preserves).
        if not dates:
            stocks = _stocks()
            if stocks is None:
                return error_payload("", _ERR)
            ref = stocks[0].get("ref_date", "") or ""
            if ref:
                dates = [ref]
                prices_by_date = [[s.get("last_price") for s in stocks]]
                rows_n = len(stocks)

        if not dates:
            return error_payload("", _ERR)

        snap = _snapshots(dates, prices_by_date)
        ranges = snap["ranges"]
        n = len(dates)
        first_counts, last_counts = snap["counts"][0], snap["counts"][-1]
        first_total, last_total = snap["totals"][0], snap["totals"][-1]
        first_shares, last_shares = snap["shares"][0], snap["shares"][-1]

        def _share_below_50(shares_row: list[float]) -> float:
            return round(sum(shares_row[:10]), 1)

        first_b50 = _share_below_50(first_shares)
        last_b50 = _share_below_50(last_shares)

        # ── KPIs (4) ────────────────────────────────────────────────────────
        kpis: list[dict[str, Any]] = [
            kpi("Snapshots Armazenados", _int(n),
                "Um snapshot por dia de sincronização em stocks_history — "
                "re-sincronizar no mesmo dia substitui o do dia; um sync "
                "em dia novo adiciona um ponto."
                + (f" {_int(rows_n)} linhas no total." if rows_n else "")),
        ]
        if n > 1:
            span_days = (_date.fromisoformat(dates[-1]) -
                         _date.fromisoformat(dates[0])).days
            kpis.append(kpi(
                "Período Coberto", f"{_int(span_days)} dias",
                f"De {_fmt_data(dates[0])} a {_fmt_data(dates[-1])} — "
                "um ponto por dia de sync (dias sem sync ficam fora da "
                "série)."))
        top_i = max(range(len(last_counts)), key=lambda i: last_counts[i])
        kpis.append(kpi(
            "Abaixo de R$ 50 — Hoje", _plain_pct(last_b50),
            (f"A fatia das ações negociadas abaixo de R$ 50 no último "
              f"snapshot ({_fmt_data(dates[-1])})."
              + (f" No primeiro ({_fmt_data(dates[0])}): "
                 f"{_plain_pct(first_b50)} — variação de "
                 f"{_pp(last_b50 - first_b50)}." if n > 1 else ""))))
        kpis.append(kpi(
            "Faixa Mais Comum — Hoje", ranges[top_i]["label"],
            f"{_int(last_counts[top_i])} ações "
            f"({_plain_pct(100.0 * last_counts[top_i] / last_total) if last_total else '0%'}) "
            "no último snapshot — a moda da distribuição."))

        # ── Sections ────────────────────────────────────────────────────────
        sections: list[dict[str, Any]] = []

        if n >= 2:
            sections.append(_evolution_chart(
                "Evolução da Distribuição — % do Total",
                _area_datasets(snap, snap["shares"]),
                dates, "% do total", "%",
                description=(
                    f"A fatia de cada faixa de preço no total de ações, "
                    f"um ponto por snapshot diário ({_int(n)} snapshots, "
                    f"{_fmt_data(dates[0])} a {_fmt_data(dates[-1])}) — as "
                    "faixas somam 100% em cada data (área 100% empilhada, "
                    "as faixas baixas embaixo: vermelho/rosa → amarelo/"
                    "verde → azul, a paleta da Visão Geral). Passe o mouse "
                    "para ler a faixa mais próxima; use a barra de período "
                    "para filtrar."
                ),
                y_max=100,
            ))
        else:
            # <2 snapshots: no one-column chart — the table + note carry it.
            pass

        # Per-date table — 5 grouped bands, newest first, sortable.
        tbl_rows: list[list[Any]] = []
        for i in reversed(range(n)):
            d = dates[i]
            c_row, s_row = snap["counts"][i], snap["shares"][i]
            total = snap["totals"][i]
            day_prices = [p for p in (prices_by_date[i] or [])
                          if p is not None]
            tip = _top3_ranges(c_row, ranges, total)
            tbl_rows.append([
                {"text": _fmt_data(d),
                 "tooltip": f"Faixas mais comuns: {tip}." if tip else ""},
                _int(total),
                *[_plain_pct(v) for v in _grouped_shares(s_row)],
                _brl(mean(day_prices)) if day_prices else "—",
            ])
        tbl = table_section(
            "Distribuição por data",
            ["Data", "Ações", *[name for name, _idx in _GROUPS],
             "Preço Médio (R$)"],
            tbl_rows,
            description=(
                "A distribuição de cada snapshot agrupada em 5 bandas de "
                "preço (as 22 faixas completas estão nos gráficos"
                + ("" if n < 2 else " acima")
                + "; o ⓘ da data carrega as 3 faixas mais comuns do dia). "
                "Mais recentes primeiro — clique no cabeçalho para ordenar."
            ),
            note=(
                "O histórico cresce um ponto por sincronização da fonte "
                "ddm-acoes (cada sync guarda o snapshot do dia; "
                "re-sincronizar no mesmo dia substitui). "
                + (f"{_int(n)} snapshot{'s' if n != 1 else ''} "
                   f"armazenado{'s' if n != 1 else ''}"
                   + (f" — de {_fmt_data(dates[0])} a {_fmt_data(dates[-1])}."
                      if n > 1 else ".")
                   if n >= 1 else "")
                + (" A evolução em gráfico ganha forma a partir do 2º "
                   "snapshot." if n < 2 else "")
            ),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        if n >= 2:
            sections.append(_evolution_chart(
                "Evolução — Nº de Ações por Faixa",
                _area_datasets(snap, snap["counts"]),
                dates, "Número de ações", " ações",
                description=(
                    "O número de ações em cada faixa ao longo do tempo "
                    "(área empilhada) — a visão absoluta do mesmo "
                    "histórico: a altura total é o número de ações "
                    "listadas em cada data (deslistagens encolhem o topo)."
                ),
            ))

        return {"status": "ok", "kpis": kpis, "sections": sections}
