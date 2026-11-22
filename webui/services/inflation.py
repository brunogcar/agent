"""webui/services/inflation.py — Mercado page / Inflação family data service (DDM).

[v1.15] The Inflação family of the ``/webui/mercado`` page — a reorganized
take on the static ``inflation_dashboard.html`` reference (built by
skills/ddm/inflation/modes/dashboard.py: 4 flat tabs — IGP-M, IPCA and INPC
each with Histórico + Matriz subtabs, plus a Comparativo tab). Fourth
family of the Mercado page (focus v1.12, fluxo v1.13, índices v1.14) —
the Brazilian price indices scraped from dadosdemercado.com.br
(IGP-M/FGV, IPCA e INPC/IBGE).

Per the v1.8–v1.14 reorganization spirit the static's gaps get fixed,
not copied:

  overview → "onde está a inflação?"        (os 9 KPI cards do estático
              (3 por índice × mês/ano/12m) viram 6 — mês + 12m por
              índice, o acumulado no ano anda no tooltip do card do mês
              (padrão v1.10/v1.13); a variação mensal dos TRÊS índices
              num único chart + o acumulado 12m sobreposto — o gráfico
              que o estático escondia na ÚLTIMA aba (Comparativo) é a
              visão de chegada; + a tabela comparativa Mês × índice —
              "quem subiu mais em outubro?" sem alternar abas)
  igpm/ipca/inpc → "como cada índice se move?"  (por índice: a evolução
              mensal — variação no mês (cheia), acumulado no ano
              (tracejada, reseta em janeiro) e acumulado 12m (pontilhada)
              — + o histórico completo + a matriz ano × mês em heatmap;
              as DUAS sub-abas do estático (Histórico + Matriz) viram
              UMA — ler a evolução e a matriz do mesmo índice exigia
              alternar)

Improvements over the static dashboard:
  - The static's Comparativo (the 3-index 12m overlay) was the LAST tab
    — the comparison lands on the overview now, next to the monthly
    variation chart (the macro:inflação two-chart precedent).
  - The per-index Histórico + Matriz subtabs merge into ONE subtab per
    index (the static made you flip to see the matrix of the index you
    were reading).
  - The comparison table (Mês × índice) is NEW — the static's per-index
    tables answered "quanto subiu o IPCA em outubro?" only one tab flip
    at a time.
  - The matrix comes from the DB (month_value per year/month + the
    year's acumulado), not the static's live page fetch — the WebUI stays
    read-only against inflation.db (the fluxo/focus precedent).
  - Skill-side PT-BR fix shipped together (modes/dashboard.py): the
    default months=0 windows rendered "Últimos 0 meses" — now "todo o
    histórico disponível".

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker — price
indices are market-wide. The adapters registry dispatches these through
the v1.11 ticker-less path and the generic endpoint
``GET /api/webui/mercado/sections/{key}`` serves them; all subtabs
render through the generic renderer (loadInflacaoSubtab → valKpisHtml +
valSectionsHtml + mountValCharts in app.js).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.inflation.query_engine`` (memory_db/ddm/
    inflation.db — index_observations: 3 slugs × ~322 monthly rows,
    2000-01 to date)

Formatting = the skill's helpers (``skills/ddm/inflation/helpers.py`` —
``format_pct`` "4,63%", ``_heat_color`` the diverging red→white→green /
sequential white→blue matrix cells). No forked numerics.

Data conventions (v1.8 fix1 / v1.9–v1.14 lineage):
  - Table months "nov/2026" (sortable — _valSortKey parses that form).
    Chart labels ship ISO "YYYY-MM" on purpose — renderValChart formats
    month axes + tooltips client-side since v1.15 and the range bar
    slices the ISO strings lexicographically.
  - Every number is a PRE-FORMATTED PT-BR string — the client only
    colorizes (negative red, % green).
  - Degradation: missing/empty inflation.db → PT-BR ``_error`` naming
    the ``ddm-inflation`` source exactly as the Sincronização page
    lists it (DDM — índices de preços).
"""
from __future__ import annotations

from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    heatmap_section,
    kpi,
    table_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.ddm.inflation.query_engine import (
    index_history as _index_history,
)

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.ddm.inflation.helpers import (
    format_pct as _pct,              # "4,63%" / "-" for None
    _heat_color as _heat_color,      # matrix cell {text, bg, color}
)

_ERR = ("Índices de preços indisponíveis — sincronize a fonte "
        "ddm-inflation (DDM — índices de preços, dadosdemercado.com.br) "
        "na página Sincronização.")

# ── index columns: slug, display name, source, chart color (the skill's
#    INDEX_COLORS static palette — same colors the static dashboard uses) ────
_INDEXES = [
    ("igp-m", "IGP-M", "FGV",  "#3b82f6"),  # blue
    ("ipca",  "IPCA",  "IBGE", "#f59e0b"),  # amber
    ("inpc",  "INPC",  "IBGE", "#a855f7"),  # purple
]
_BY_SLUG = {s: (n, src, c) for s, n, src, c in _INDEXES}

# [v3 skill pattern] Lighter 300-shade for the dashed "Acumulado no ano"
# line (INDEX_COLORS_ACUM_ANO mirrors).
_ACUM_ANO_COLOR = {"igp-m": "#93c5fd", "ipca": "#fcd34d", "inpc": "#d8b4fe"}
_C_12M = "#94a3b8"   # slate — the dotted 12m line (skill pattern)

_BR_MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez")
_MONTH_LABELS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                 "Jul", "Ago", "Set", "Out", "Nov", "Dez")

_MONTHS_TABLE = 24   # overview comparison table window (macro precedent)


# ── helpers ─────────────────────────────────────────────────────────────────
def _br_month(ym: Any) -> Any:
    """'2026-11' → 'nov/2026' (short PT-BR month, sortable by _valSortKey)."""
    if isinstance(ym, str) and len(ym) == 7 and ym[4] == "-":
        m = int(ym[5:7])
        if 1 <= m <= 12:
            return f"{_BR_MONTHS[m - 1]}/{ym[0:4]}"
    return ym


def _series(slug: str) -> dict[str, Any] | None:
    """index_history(slug) normalized; None on any failure/no data."""
    try:
        res = _index_history(slug=slug, limit=0)
    except Exception:
        return None
    if res.get("status") != "ok":
        return None
    obs = [o for o in res.get("observations", []) if o.get("ref_date")]
    return {"slug": slug, "observations": obs} if obs else None


def _snapshot() -> dict[str, Any]:
    """Every index series in ONE pass; ``_error`` payload on total failure.

    One snapshot serves every subtab (each series is ~322 monthly rows —
    the static dashboard itself slices single index_history() calls in
    memory). Partial syncs degrade gracefully: the views show whatever
    synced, the per-index subtabs name their own index when missing.
    """
    series = [s for s in (_series(slug) for slug, *_ in _INDEXES) if s]
    if not series:
        return {"_error": _ERR}
    return {"series": series}


def _last(obs: list[dict[str, Any]]) -> dict[str, Any]:
    return obs[-1] if obs else {}


def _line_ds(label: str, data: list[Any], color: str, *,
             dash: list[int] | None = None) -> dict[str, Any]:
    """One line dataset (server styling is honored by renderValChart)."""
    ds: dict[str, Any] = {
        "label": label, "data": data,
        "borderColor": color, "backgroundColor": color,
        "borderWidth": 2, "pointRadius": 0,
        "pointHoverRadius": 4, "tension": 0.25, "fill": False,
    }
    if dash:
        ds["borderDash"] = dash
    return ds


def _month_chart(title: str, datasets: list[dict[str, Any]],
                 labels: list[str], y_title: str = "%",
                 description: str = "") -> dict[str, Any]:
    """Line chart over ISO YYYY-MM labels + the client-side range bar.

    Monthly labels ship ISO on purpose: renderValChart formats month axes
    + tooltips ("nov/2026") client-side since v1.15, and valChartRange
    slices the ISO strings lexicographically (same contract as the daily
    YYYY-MM-DD charts since v1.7.2).
    """
    cd: dict[str, Any] = {
        "type": "line",
        "data": {"labels": labels, "datasets": datasets},
        "options": {"scales": {"y": {"title": {"display": True,
                                               "text": y_title}}}},
    }
    sec = chart_section(title, cd, description=description)
    sec["price_range_selector"] = True   # client-side range bar
    return sec


def _matrix_rows(observations: list[dict[str, Any]]) -> list[list[Any]]:
    """Year × month matrix from the DB series (DESC by year, newest first).

    Jan–Dez cells = month_value; the final "Ano" cell = the year's
    acumulado (year_acumulado of the latest month with data — the same
    number the DDM page's matrix shows). Cells carry the skill's
    _heat_color dicts: diverging red→white→green for the months,
    sequential white→blue for the year column; min/max computed from the
    actual data (no hardcoded values).
    """
    years: dict[str, dict[str, float]] = {}
    year_acum: dict[str, float] = {}
    for o in observations:                      # obs are ASC
        ym = o.get("ref_date", "")
        if len(ym) != 7:
            continue
        y, m = ym[:4], ym[5:7]
        row = years.setdefault(y, {})
        if o.get("month_value") is not None:
            row[m] = o["month_value"]
        if o.get("year_acumulado") is not None:
            year_acum[y] = o["year_acumulado"]  # last one wins (ASC)

    if not years:
        return []

    monthly_vals = [v for row in years.values() for v in row.values()]
    annual_vals = list(year_acum.values())
    m_min, m_max = (min(monthly_vals), max(monthly_vals)) if monthly_vals \
        else (0.0, 0.0)
    a_min, a_max = (min(annual_vals), max(annual_vals)) if annual_vals \
        else (0.0, 0.0)

    rows: list[list[Any]] = []
    for y in sorted(years, reverse=True):       # newest year first
        row = years[y]
        out: list[Any] = [y]
        for i in range(1, 13):
            mm = f"{i:02d}"
            out.append(_heat_color(row.get(mm), m_min, m_max, "diverging"))
        out.append(_heat_color(year_acum.get(y), a_min, a_max, "sequential"))
        rows.append(out)
    return rows


# ── service ─────────────────────────────────────────────────────────────────
class InflationService:
    """Mercado page / Inflação family — 4 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """Onde está a inflação — os 3 índices lado a lado.

        Landing subtab: the COMPARISON view (the static's gap: its 12m
        overlay was the LAST tab and the 9 KPI cards mixed 3 indices × 3
        windows). Monthly variation + 12m acumulado of all three indices
        in two charts, the per-index detail in its own subtabs.
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        series = snap["series"]
        kpis: list[dict[str, Any]] = []
        for s in series:
            name, _src, _c = _BY_SLUG[s["slug"]]
            last = _last(s["observations"])
            kpis.append(kpi(
                f"{name} — mês",
                _pct(last.get("month_value")),
                f"Variação de {_br_month(last.get('ref_date'))} · "
                f"acumulado no ano: {_pct(last.get('year_acumulado'))}. "
                f"Fonte: {_BY_SLUG[s['slug']][1]} via "
                "dadosdemercado.com.br.",
            ))
            kpis.append(kpi(
                f"{name} — 12m",
                _pct(last.get("acumulado_12m")),
                "Soma das variações dos últimos 12 meses (janela móvel) "
                "— a leitura de inflação que o BCB acompanha para a "
                "meta.",
            ))

        # Union of all months (ASC) — one x axis shared by both charts.
        all_ym: list[str] = []
        seen: set[str] = set()
        for s in series:
            for o in s["observations"]:
                d = o["ref_date"]
                if d not in seen:
                    seen.add(d)
                    all_ym.append(d)
        all_ym.sort()

        def _by_date(s: dict[str, Any], field: str) -> list[Any]:
            m = {o["ref_date"]: o.get(field) for o in s["observations"]}
            return [m.get(d) for d in all_ym]

        sections: list[dict[str, Any]] = [
            _month_chart(
                "Variação mensal — IGP-M vs IPCA vs INPC",
                [
                    _line_ds(_BY_SLUG[s["slug"]][0],
                             _by_date(s, "month_value"),
                             _BY_SLUG[s["slug"]][2])
                    for s in series
                ],
                all_ym, y_title="% (a.m.)",
                description=(
                    "A variação percentual de cada mês, os três índices "
                    "lado a lado (uma linha por índice). O estático "
                    "exigia alternar entre as abas IGP-M, IPCA e INPC "
                    "para comparar o mesmo mês. Use a barra de período "
                    "para filtrar."
                ),
            ),
            _month_chart(
                "Acumulado 12 meses — IGP-M vs IPCA vs INPC",
                [
                    _line_ds(_BY_SLUG[s["slug"]][0],
                             _by_date(s, "acumulado_12m"),
                             _BY_SLUG[s["slug"]][2])
                    for s in series
                ],
                all_ym, y_title="% (acum. 12m)",
                description=(
                    "A soma das variações dos últimos 12 meses (janela "
                    "móvel), uma linha por índice — a leitura que o BCB "
                    "acompanha para a meta. No estático este gráfico era "
                    "a última aba (Comparativo); aqui é a visão de "
                    "chegada."
                ),
            ),
        ]

        # Comparison table — newest first, last 24 months (macro
        # precedent). The month cell's ⓘ carries the 12m reading of
        # every index for that month (tooltips render on the first
        # column — the v1.8 renderer contract).
        by_slug = {s["slug"]: s for s in series}
        rows = []
        for ym in reversed(all_ym[-_MONTHS_TABLE:]):
            row: list[Any] = [_br_month(ym)]
            tips = []
            for slug, name, _src, _c in _INDEXES:
                s = by_slug.get(slug)
                obs = {o["ref_date"]: o for o in s["observations"]} if s else {}
                o = obs.get(ym, {})
                row.append(_pct(o.get("month_value")))
                a12 = o.get("acumulado_12m")
                if a12 is not None:
                    tips.append(f"{name} 12m: {_pct(a12)}")
            if tips:
                row[0] = {"text": _br_month(ym),
                          "tooltip": f"Acumulado 12m — {' · '.join(tips)}."}
            rows.append(row)

        tbl = table_section(
            "Comparativo mensal",
            ["Mês", *[ _BY_SLUG[s["slug"]][0] for s in series ]],
            rows,
            description=(
                "A variação de cada mês, os três índices lado a lado "
                f"(mais recentes primeiro — últimos {_MONTHS_TABLE} "
                "meses). O ⓘ de cada mês carrega o acumulado 12m de "
                "cada índice naquela leitura."
            ),
            note=("O histórico completo de cada índice e a matriz "
                  "ano × mês estão nas subabas IGP-M, IPCA e INPC."),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Per-index views (IGP-M / IPCA / INPC) ───────────────────────────────
    def _index_view(self, slug: str) -> dict[str, Any]:
        """Como cada índice se move — evolução + histórico + matriz.

        The static's per-index Histórico + Matriz subtabs merged into ONE
        subtab (its gap: reading one index's evolution and its matrix
        required a subtab flip). The evolução chart keeps the static's
        3-line design: variação no mês (cheia), acumulado no ano
        (tracejada, reseta em janeiro), acumulado 12m (pontilhada).
        """
        name, source, color = _BY_SLUG[slug]
        s = _series(slug)
        if s is None:
            return error_payload("", (
                f"O índice {name} está indisponível — sincronize a fonte "
                "ddm-inflation (DDM — índices de preços) na página "
                "Sincronização."))

        obs = s["observations"]
        last = _last(obs)
        labels = [o["ref_date"] for o in obs]
        first_year = labels[0][:4] if labels else ""
        last_year = labels[-1][:4] if labels else ""

        kpis = [
            kpi(f"{name} — mês", _pct(last.get("month_value")),
                f"Variação de {_br_month(last.get('ref_date'))} · "
                f"acumulado no ano: {_pct(last.get('year_acumulado'))}."),
            kpi(f"{name} — ano", _pct(last.get("year_acumulado")),
                f"Acumulado no ano corrente (jan a "
                f"{_br_month(last.get('ref_date'))})."),
            kpi(f"{name} — 12m", _pct(last.get("acumulado_12m")),
                "Soma das variações dos últimos 12 meses (janela móvel). "
                f"Fonte: {source} via dadosdemercado.com.br."),
        ]

        sections: list[dict[str, Any]] = [
            _month_chart(
                "Evolução mensal",
                [
                    _line_ds("Variação no mês (%)",
                             [o.get("month_value") for o in obs], color),
                    _line_ds("Acumulado no ano (%)",
                             [o.get("year_acumulado") for o in obs],
                             _ACUM_ANO_COLOR[slug], dash=[5, 5]),
                    _line_ds("Acumulado 12 meses (%)",
                             [o.get("acumulado_12m") for o in obs],
                             _C_12M, dash=[2, 4]),
                ],
                labels,
                description=(
                    f"Variação mensal (linha cheia), acumulado no ano "
                    f"(tracejada — reseta em 1º de janeiro) e acumulado "
                    f"12 meses (pontilhada) do {name}. Todo o histórico "
                    f"disponível ({first_year} a {last_year}); use a "
                    "barra de período para filtrar."
                ),
            ),
        ]

        # Full history table — newest first (static convention), sortable.
        rows = [
            [_br_month(o["ref_date"]),
             _pct(o.get("month_value")),
             _pct(o.get("year_acumulado")),
             _pct(o.get("acumulado_12m"))]
            for o in reversed(obs)
        ]
        tbl = table_section(
            "Histórico mensal",
            ["Mês", "Índice do mês (%)", "Acumulado no ano (%)",
             "Acumulado 12m (%)"],
            rows,
            description=(
                "Todas as observações (mais recentes primeiro). Clique "
                "no cabeçalho para ordenar — a coluna Mês ordena "
                "cronologicamente."
            ),
            note=(f"{len(rows)} observações sincronizadas — a matriz "
                  "ano × mês abaixo resume este histórico em heatmap."),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        # Year × month heatmap — computed from the DB (the static's
        # monthly_matrix live-fetch stays in the skill; the WebUI is
        # read-only against inflation.db).
        matrix = _matrix_rows(obs)
        if matrix:
            sections.append(heatmap_section(
                "Matriz ano × mês",
                ["Ano", *_MONTH_LABELS, "Ano"],
                matrix,
                description=(
                    "Matriz ano × mês. Coluna final 'Ano' é o acumulado "
                    "no ano. Cores: vermelho=negativo, branco=zero, "
                    "verde=positivo (mensal); branco→azul (anual)."
                ),
            ))

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── IGP-M ───────────────────────────────────────────────────────────────
    def igpm(self) -> dict[str, Any]:
        """IGP-M — Índice Geral de Preços - Mercado (FGV)."""
        return self._index_view("igp-m")

    # ── IPCA ────────────────────────────────────────────────────────────────
    def ipca(self) -> dict[str, Any]:
        """IPCA — Índice Nacional de Preços ao Consumidor Amplo (IBGE)."""
        return self._index_view("ipca")

    # ── INPC ────────────────────────────────────────────────────────────────
    def inpc(self) -> dict[str, Any]:
        """INPC — Índice Nacional de Preços ao Consumidor (IBGE)."""
        return self._index_view("inpc")
