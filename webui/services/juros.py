"""webui/services/juros.py — Mercado page / Juros family data service (DDM).

[v1.16] The Juros family of the ``/webui/mercado`` page — a reorganized
take on the static ``juros_dashboard.html`` reference (built by
skills/ddm/juros/modes/dashboard.py: 4 flat tabs — Selic, Meta Selic and
CDI each with Histórico + Matriz subtabs, plus a Comparativo tab). Fifth
family of the Mercado page (focus v1.12, fluxo v1.13, índices v1.14,
inflação v1.15) — the Brazilian interest rates scraped from
the DDM source (Selic/BCB, Meta Selic/Copom, CDI/interbank).

Per the v1.8–v1.15 reorganization spirit the static's gaps get fixed,
not copied:

  overview → "onde estão os juros?"          (os 9 KPI cards do estático
              (3 por taxa × mês/média ano/média 12m) viram 6 — mês +
              12m por taxa, a média no ano anda no tooltip do card do mês
              (padrão v1.10/v1.13/v1.15); a taxa efetiva dos TRÊS índices
              num único chart + a média 12m sobreposta — o gráfico que o
              estático escondia na ÚLTIMA aba (Comparativo) é a visão de
              chegada; + a tabela comparativa Mês × taxa — "a CDI está
              colada na Selic?" sem alternar abas)
  selic/meta_selic/cdi → "como cada taxa se move?"  (por taxa: a evolução
              mensal — taxa do mês (cheia), média no ano (tracejada, anda
              com o Copom) e média 12m (pontilhada) — + a matriz ano × mês
              em heatmap ANTES do histórico completo ([v1.23] — o ano
              inteiro num relance primeiro; o Histórico mensal vem
              RECOLHIDO, abre sob demanda) — as DUAS sub-abas do estático
              (Histórico + Matriz) viram UMA — ler a evolução e a matriz
              da mesma taxa exigia alternar)

Improvements over the static dashboard:
  - The static's Comparativo (the 3-rate overlay) was the LAST tab — the
    comparison lands on the overview now, next to the effective-rate
    chart (the inflação v1.15 precedent).
  - The per-rate Histórico + Matriz subtabs merge into ONE subtab per
    rate (the static made you flip to see the matrix of the rate you
    were reading).
  - The comparison table (Mês × taxa) is NEW — the static's per-rate
    tables answered "qual a Selic em outubro?" only one tab flip at a
    time.
  - The matrix comes from the DB (month_value per year/month), not the
    static's live page fetch — the WebUI stays read-only against
    juros.db (the fluxo/focus/inflação precedent; the live-fetch
    monthly_matrix stays in the skill).
  - Juros are RATES, not acumulados: the matrix carries NO "Ano" column
    (the skill's convention — you don't accumulate a % a.a. rate), and
    the 12m line is a rolling AVERAGE, not a sum.
  - Meta Selic runs one month ahead when the Copom has announced the
    next meta (dez/2026 while Selic/CDI stop at nov/2026) — the
    meta_selic view says so instead of letting the extra point look like
    a data glitch.
  - Skill-side PT-BR fix shipped together (modes/dashboard.py v2): the
    default months=0 windows rendered "Últimos 0 meses" — now "todo o
    histórico disponível" (the inflation v3.1 fix, mirrored).

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker —
interest rates are market-wide. The adapters registry dispatches these
through the v1.11 ticker-less path and the generic endpoint
``GET /api/webui/mercado/sections/{key}`` serves them; all subtabs
render through the generic renderer (loadJurosSubtab → valKpisHtml +
valSectionsHtml + mountValCharts in app.js).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.juros.query_engine`` (memory_db/ddm/juros.db —
    juros_observations: 3 slugs × ~323 monthly rows, 2000-01 to date;
    month_value / media_no_ano / media_12m)

Formatting = the skill's helpers (``skills/ddm/juros/helpers.py`` —
``format_pct`` "13,65%", ``_heat_color`` the diverging red→white→green
matrix cells). No forked numerics.

Data conventions (v1.8 fix1 / v1.9–v1.15 lineage):
  - Table months "nov/2026" (sortable — _valSortKey parses that form).
    Chart labels ship ISO "YYYY-MM" on purpose — renderValChart formats
    month axes + tooltips client-side since v1.15 and the range bar
    slices the ISO strings lexicographically.
  - Every number is a PRE-FORMATTED PT-BR string — the client only
    colorizes (negative red, % green).
  - Degradation: missing/empty juros.db → PT-BR ``_error`` naming the
    ``ddm-juros`` source exactly as the Sincronização page lists it
    (DDM — juros).
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
from data_sources.ddm.juros.query_engine import (
    juros_history as _juros_history,
)

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.ddm.juros.helpers import (
    format_pct as _pct,              # "13,65%" / "-" for None
    _heat_color as _heat_color,      # matrix cell {text, bg, color}
)

_ERR = ("Taxas de juros indisponíveis — sincronize a fonte "
        "ddm-juros (DDM — juros) na página "
        "Sincronização.")

# ── rate columns: slug, display name, source, chart color (the skill's
#    INDEX_COLORS static palette — same colors the static dashboard uses) ────
_RATES = [
    ("selic",      "Selic",      "BCB",               "#0d9488"),  # teal
    ("meta-selic", "Meta Selic", "Copom",             "#3b82f6"),  # blue
    ("cdi",        "CDI",        "mercado interbancário", "#f59e0b"),  # amber
]
_BY_SLUG = {s: (n, src, c) for s, n, src, c in _RATES}

# [skill pattern] Lighter 300-shade for the dashed "Média no ano" line
# (INDEX_COLORS_MEDIA_ANO mirrors).
_MEDIA_ANO_COLOR = {"selic": "#5eead4", "meta-selic": "#93c5fd",
                    "cdi": "#fcd34d"}
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
    """juros_history(slug) normalized; None on any failure/no data."""
    try:
        res = _juros_history(slug=slug, limit=0)
    except Exception:
        return None
    if res.get("status") != "ok":
        return None
    obs = [o for o in res.get("observations", []) if o.get("ref_date")]
    return {"slug": slug, "observations": obs} if obs else None


def _snapshot() -> dict[str, Any]:
    """Every rate series in ONE pass; ``_error`` payload on total failure.

    One snapshot serves every subtab (each series is ~323 monthly rows —
    the static dashboard itself slices single juros_history() calls in
    memory). Partial syncs degrade gracefully: the views show whatever
    synced, the per-rate subtabs name their own rate when missing.
    """
    series = [s for s in (_series(slug) for slug, *_ in _RATES) if s]
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
                 labels: list[str], y_title: str = "% a.a.",
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

    Jan–Dez cells = month_value (the effective rate of that month). NO
    final "Ano" cell — juros are daily rates (% a.a.), not acumulados to
    sum (the skill's convention). Cells carry the skill's _heat_color
    dicts: diverging red→white→green with min/max computed from the
    actual data (no hardcoded values — low rates red, high rates green,
    midpoint white).
    """
    years: dict[str, dict[str, float]] = {}
    for o in observations:                      # obs are ASC
        ym = o.get("ref_date", "")
        if len(ym) != 7:
            continue
        y, m = ym[:4], ym[5:7]
        if o.get("month_value") is not None:
            years.setdefault(y, {})[m] = o["month_value"]

    if not years:
        return []

    monthly_vals = [v for row in years.values() for v in row.values()]
    m_min, m_max = (min(monthly_vals), max(monthly_vals)) if monthly_vals \
        else (0.0, 0.0)

    rows: list[list[Any]] = []
    for y in sorted(years, reverse=True):       # newest year first
        row = years[y]
        out: list[Any] = [y]
        for i in range(1, 13):
            mm = f"{i:02d}"
            out.append(_heat_color(row.get(mm), m_min, m_max))
        rows.append(out)
    return rows


# ── service ─────────────────────────────────────────────────────────────────
class JurosService:
    """Mercado page / Juros family — 4 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """Onde estão os juros — as três taxas lado a lado.

        Landing subtab: the COMPARISON view (the static's gap: its
        overlay was the LAST tab and the 9 KPI cards mixed 3 rates × 3
        windows). Effective rate + rolling 12m average of all three
        rates in two charts, the per-rate detail in its own subtabs.
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
                f"Taxa de {_br_month(last.get('ref_date'))} · "
                f"média no ano: {_pct(last.get('media_no_ano'))}. "
                f"Fonte: {_BY_SLUG[s['slug']][1]}.",
            ))
            kpis.append(kpi(
                f"{name} — 12m",
                _pct(last.get("media_12m")),
                "Média das taxas dos últimos 12 meses (janela móvel) — "
                "a leitura de nível de juros que suaviza os movimentos "
                "do Copom.",
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
                "Taxa mensal — Selic vs Meta Selic vs CDI",
                [
                    _line_ds(_BY_SLUG[s["slug"]][0],
                             _by_date(s, "month_value"),
                             _BY_SLUG[s["slug"]][2])
                    for s in series
                ],
                all_ym,
                description=(
                    "A taxa efetiva de cada mês (% a.a.), as três taxas "
                    "lado a lado (uma linha por taxa). O estático "
                    "exigia alternar entre as abas Selic, Meta Selic e "
                    "CDI para comparar o mesmo mês. Use a barra de "
                    "período para filtrar."
                ),
            ),
            _month_chart(
                "Média 12 meses — Selic vs Meta Selic vs CDI",
                [
                    _line_ds(_BY_SLUG[s["slug"]][0],
                             _by_date(s, "media_12m"),
                             _BY_SLUG[s["slug"]][2])
                    for s in series
                ],
                all_ym, y_title="% (média 12m)",
                description=(
                    "A média das taxas dos últimos 12 meses (janela "
                    "móvel), uma linha por taxa — a leitura de nível "
                    "que suaviza os movimentos do Copom. No estático "
                    "este gráfico era a última aba (Comparativo); aqui "
                    "é a visão de chegada."
                ),
            ),
        ]

        # Comparison table — newest first, last 24 months (macro
        # precedent). The month cell's ⓘ carries the 12m average of
        # every rate for that month (tooltips render on the first
        # column — the v1.8 renderer contract).
        by_slug = {s["slug"]: s for s in series}
        rows = []
        for ym in reversed(all_ym[-_MONTHS_TABLE:]):
            row: list[Any] = [_br_month(ym)]
            tips = []
            for slug, name, _src, _c in _RATES:
                s = by_slug.get(slug)
                obs = {o["ref_date"]: o for o in s["observations"]} if s else {}
                o = obs.get(ym, {})
                row.append(_pct(o.get("month_value")))
                m12 = o.get("media_12m")
                if m12 is not None:
                    tips.append(f"{name} 12m: {_pct(m12)}")
            if tips:
                row[0] = {"text": _br_month(ym),
                          "tooltip": f"Média 12m — {' · '.join(tips)}."}
            rows.append(row)

        tbl = table_section(
            "Comparativo mensal",
            ["Mês", *[ _BY_SLUG[s["slug"]][0] for s in series ]],
            rows,
            description=(
                "A taxa efetiva de cada mês, as três taxas lado a lado "
                f"(mais recentes primeiro — últimos {_MONTHS_TABLE} "
                "meses). O ⓘ de cada mês carrega a média 12m de cada "
                "taxa naquela leitura."
            ),
            note=("O histórico completo de cada taxa e a matriz "
                  "ano × mês estão nas subabas Selic, Meta Selic e CDI. "
                  "A Meta Selic pode andar um mês à frente quando o "
                  "Copom já anunciou a próxima meta."),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Per-rate views (Selic / Meta Selic / CDI) ───────────────────────────
    def _rate_view(self, slug: str) -> dict[str, Any]:
        """Como cada taxa se move — evolução + histórico + matriz.

        The static's per-rate Histórico + Matriz subtabs merged into ONE
        subtab (its gap: reading one rate's evolution and its matrix
        required a subtab flip). The evolução chart keeps the static's
        3-line design: taxa do mês (cheia), média no ano (tracejada,
        acompanha o Copom), média 12m (pontilhada).
        """
        name, source, color = _BY_SLUG[slug]
        s = _series(slug)
        if s is None:
            return error_payload("", (
                f"A taxa {name} está indisponível — sincronize a fonte "
                "ddm-juros (DDM — juros) na página Sincronização."))

        obs = s["observations"]
        last = _last(obs)
        labels = [o["ref_date"] for o in obs]
        first_year = labels[0][:4] if labels else ""
        last_year = labels[-1][:4] if labels else ""

        kpis = [
            kpi(f"{name} — mês", _pct(last.get("month_value")),
                f"Taxa de {_br_month(last.get('ref_date'))} · "
                f"média no ano: {_pct(last.get('media_no_ano'))}."),
            kpi(f"{name} — média no ano", _pct(last.get("media_no_ano")),
                f"Média das taxas de jan a "
                f"{_br_month(last.get('ref_date'))} (o ano em curso)."),
            kpi(f"{name} — 12m", _pct(last.get("media_12m")),
                "Média das taxas dos últimos 12 meses (janela móvel). "
                f"Fonte: {source}."),
        ]

        # Meta Selic runs one month ahead when the next meta is already
        # announced — say so, or the extra point looks like a glitch.
        ahead = (" A meta é definida nas reuniões do Copom — esta série "
                 "pode andar um mês à frente das taxas efetivas (Selic "
                 "e CDI) quando a próxima meta já foi anunciada."
                 if slug == "meta-selic" else "")

        sections: list[dict[str, Any]] = [
            _month_chart(
                "Evolução mensal",
                [
                    _line_ds("Taxa do mês (% a.a.)",
                             [o.get("month_value") for o in obs], color),
                    _line_ds("Média no ano (%)",
                             [o.get("media_no_ano") for o in obs],
                             _MEDIA_ANO_COLOR[slug], dash=[5, 5]),
                    _line_ds("Média 12 meses (%)",
                             [o.get("media_12m") for o in obs],
                             _C_12M, dash=[2, 4]),
                ],
                labels,
                description=(
                    f"Taxa do mês (linha cheia), média no ano (tracejada "
                    f"— acompanha o Copom ao longo do ano) e média 12 "
                    f"meses (pontilhada) do {name}. Todo o histórico "
                    f"disponível ({first_year} a {last_year}); use a "
                    f"barra de período para filtrar.{ahead}"
                ),
            ),
        ]

        # [v1.23] The matrix comes FIRST — the year-at-a-glance read
        # leads, and the full Histórico mensal follows COLLAPSED (the
        # same numbers, one row per month; the summary carries the row
        # count — opens on demand). The old order buried the matrix
        # under ~323 table rows. NO "Ano" column: rates, not acumulados
        # (the skill's convention).
        matrix = _matrix_rows(obs)
        if matrix:
            sections.append(heatmap_section(
                "Matriz ano × mês",
                ["Ano", *_MONTH_LABELS],
                matrix,
                description=(
                    "Matriz ano × mês da taxa efetiva (% a.a.). NÃO há "
                    "coluna 'Ano' — juros são taxas, não acumulados a "
                    "somar. Cores: vermelho=taxas baixas, branco=ponto "
                    "médio do histórico, verde=taxas altas."
                ),
            ))

        # Full history table — newest first (static convention), sortable,
        # COLLAPSED (v1.23: the matrix above already answers the year
        # reads; the row-by-row ledger opens on demand).
        rows = [
            [_br_month(o["ref_date"]),
             _pct(o.get("month_value")),
             _pct(o.get("media_no_ano")),
             _pct(o.get("media_12m"))]
            for o in reversed(obs)
        ]
        tbl = table_section(
            "Histórico mensal",
            ["Mês", "Taxa do mês (% a.a.)", "Média no ano (%)",
             "Média 12m (%)"],
            rows,
            description=(
                "Todas as observações (mais recentes primeiro). Clique "
                "no cabeçalho para ordenar — a coluna Mês ordena "
                "cronologicamente."
            ),
            note=(f"{len(rows)} observações sincronizadas — a matriz "
                  "ano × mês acima resume este histórico em heatmap."),
        )
        tbl["sortable"] = True
        tbl["collapsed"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Selic ───────────────────────────────────────────────────────────────
    def selic(self) -> dict[str, Any]:
        """Selic — Taxa Selic diária (BCB), % a.a."""
        return self._rate_view("selic")

    # ── Meta Selic ──────────────────────────────────────────────────────────
    def meta_selic(self) -> dict[str, Any]:
        """Meta Selic — a meta do Copom para a taxa Selic, % a.a."""
        return self._rate_view("meta-selic")

    # ── CDI ─────────────────────────────────────────────────────────────────
    def cdi(self) -> dict[str, Any]:
        """CDI — Certificado de Depósito Interbancário, % a.a."""
        return self._rate_view("cdi")
