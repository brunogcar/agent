"""webui/services/focus.py — Mercado page / Focus family data service (DDM).

[v1.12] The Focus family of the ``/webui/mercado`` page — a reorganized
take on the static ``focus_dashboard.html`` reference (built by
skills/ddm/focus/modes/dashboard.py, 13 flat tabs: 1 Focus overview with
4 year subtabs + 12 per-indicator tabs). The Mercado page is the new home
for the DDM dashboards (focus now; dividends, índices, fluxo, inflação
and juros as later families) — market-level data from
dadosdemercado.com.br, next to Macro (realized BCB SGS indicators).

Per the v1.12 design the LANDING subtab carries the general content (the
static's Focus tab — the Boletim summary, one table per reference year)
and the 12 per-indicator tabs are regrouped into 6 question-driven
subtabs (the v1.8–v1.11 reorganization spirit — the static's parallel
by-indicator navigation collapses into themed groups):

  overview   → "o que o mercado projeta?"     (KPIs + Boletim Focus,
                                               one table per ano)
  inflacao   → IPCA + IPCA Adm + IGP-M        (expectativas de preços)
  atividade  → PIB Total                      (crescimento)
  juros      → Selic                          (taxas)
  cambio     → Câmbio                         (dólar)
  externo    → Conta corrente + Balança       (contas externas)
               comercial + Investimento direto
  fiscal     → Dívida líquida setor pub +     (contas públicas)
               Resultado primário + nominal

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker — the
Boletim Focus is market-wide. The adapters registry dispatches these
through the v1.11 ticker-less path and the generic endpoint
``GET /api/webui/mercado/sections/{key}`` serves them; all subtabs
render through the generic renderer (loadFocusSubtab → valKpisHtml +
valSectionsHtml + mountValCharts in app.js).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.focus.query_engine`` (memory_db/ddm/focus.db —
    the weekly Boletim snapshot scraped from dadosdemercado.com.br)

Formatting = the skill's helpers (``skills/ddm/focus/helpers.py`` —
``format_value`` carries the per-indicator unit: % (4 dec), R$ (2 dec),
US$ mi (0 dec); ``comparison_symbol`` ▲/▼/=). No forked numerics.

Improvements over the static dashboard (same reorganization spirit as
v1.8–v1.11 — the static gaps get fixed, not copied):
  - The 12 near-identical indicator tabs (each: 1 chart + 1 4-row table)
    become 6 themed subtabs — related expectations (IPCA vs IGP-M vs
    IPCA Adm; the three external accounts; the three fiscal results)
    sit together, each with its own KPI card instead of a bare chart.
  - KPI cards per subtab: the "Hoje" expectation for the current year,
    tooltip carrying every year + the 4-week comparison + respondents
    (the static showed no KPIs outside the overview).
  - Degradation: missing focus.db → PT-BR ``_error`` naming the
    ``ddm-focus`` source exactly as the Sincronização page lists it.

Data conventions (v1.8 fix1 / v1.9–v1.11 lineage):
  - The one user-visible date (Data de referência) is dd/mm/yyyy via
    ``_fmt_date``; years are plain integers.
  - Every number is a PRE-FORMATTED PT-BR string from the skill's
    ``format_value`` (comma decimals) — the client only colorizes.
"""
from __future__ import annotations

from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    kpi,
    table_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.ddm.focus.query_engine import all_data as _all_data
from data_sources.ddm.focus.query_engine import summary as _summary

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.ddm.focus.helpers import format_int, format_value

# ── time windows (mirror skills/ddm/focus/modes/dashboard.py) ───────────────
_WINDOWS = [
    ("four_weeks_ago", "Há 4 semanas"),
    ("one_week_ago",   "1 sem"),
    ("today",          "Hoje"),
]

# ── indicator groups: the static's 12 per-indicator tabs regrouped by
#    question (v1.8–v1.11 reorganization spirit) ─────────────────────────────
_GROUPS: dict[str, list[str]] = {
    "inflacao": ["IPCA", "IPCA Adm", "IGP-M"],
    "atividade": ["PIB Total"],
    "juros": ["Selic"],
    "cambio": ["Câmbio"],
    "externo": ["Conta corrente", "Balança comercial",
                "Investimento direto no país"],
    "fiscal": ["Dívida líquida setor pub", "Resultado primário",
               "Resultado nominal"],
}

# ── per-indicator y-axis unit (mirrors skills/ddm/focus/helpers
#    _INDICATOR_UNITS — kept local so the private map stays private) ─────────
_UNIT: dict[str, str] = {
    "IPCA":               "%",
    "PIB Total":          "%",
    "Selic":              "%",
    "IGP-M":              "%",
    "IPCA Adm":           "%",
    "Dívida líquida setor pub": "%",
    "Resultado primário": "%",
    "Resultado nominal":  "%",
    "Câmbio":             "R$",
    "Conta corrente":     "US$ mi",
    "Balança comercial":  "US$ mi",
    "Investimento direto no país": "US$ mi",
}

# ── palette (same accents as the WebUI macro page) ──────────────────────────
_C_4W  = "#0d9488"   # teal    — Há 4 semanas
_C_1W  = "#f59e0b"   # amber   — 1 sem
_C_TOD = "#3b82f6"   # blue    — Hoje
_WINDOW_COLORS = {"four_weeks_ago": _C_4W, "one_week_ago": _C_1W,
                  "today": _C_TOD}

_COMP_GLYPH = {"up": "▲", "down": "▼"}   # anything else → "="


# ── helpers ─────────────────────────────────────────────────────────────────
def _fmt_date(s: Any) -> Any:
    """ISO YYYY-MM-DD → dd/mm/yyyy (v1.8 fix1 convention; passthrough)."""
    if isinstance(s, str) and len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _snapshot() -> dict[str, Any]:
    """all_data() + summary() merged; ``_error`` payload on any failure.

    One snapshot serves every subtab (the Boletim is 4 years × 12
    indicators ≈ 48 rows — the static dashboard itself slices a single
    all_data() call in memory).
    """
    data = _all_data()
    if data.get("status") != "ok":
        return {"_error": (
            "Boletim Focus indisponível — sincronize a fonte ddm-focus "
            "(DDM — Boletim Focus, dadosdemercado.com.br) na página "
            "Sincronização.")}
    summ = _summary()
    obs: list[dict[str, Any]] = data.get("observations", [])
    if not obs and summ.get("status") == "ok":
        return {"_error": (
            "Boletim Focus vazio — a fonte ddm-focus sincronizou sem "
            "observações. Rode a sincronização novamente na página "
            "Sincronização.")}
    return {
        "ref_date": data.get("ref_date", ""),
        "synced_at": data.get("synced_at", ""),
        "observations": obs,
        "years": summ.get("years", []) or sorted({o.get("year") for o in obs
                                                  if o.get("year")}),
        "indicator_count": summ.get("indicator_count"),
        "row_count": summ.get("row_count"),
    }


def _by_indicator(obs: list[dict[str, Any]],
                  indicator: str) -> list[dict[str, Any]]:
    """One indicator' rows, year ASC (the snapshot is year ASC already)."""
    return [o for o in obs if o.get("indicator") == indicator]


def _fmt(v: Any, indicator: str) -> str:
    """format_value(None) → '-'; the skill handles units + PT-BR."""
    return format_value(v, indicator)


def _kpi_for(obs: list[dict[str, Any]], indicator: str,
             years: list[int]) -> dict[str, Any]:
    """One KPI card: Hoje for the current year, tooltip with every year.

    The current year = the earliest covered year (the Boletim targets
    the running year first — 2026 while it runs). Tooltip carries the
    per-year expectations + the 4-week comparison + respondents, so the
    landing skim answers "what changed this week".
    """
    cur_year = min(years) if years else None
    cur = next((o for o in obs if o.get("year") == cur_year), None)
    unit = _UNIT.get(indicator, "")
    value = _fmt(cur.get("today") if cur else None, indicator)
    tip = (f"Expectativa 'Hoje' do Boletim Focus para {indicator}"
           + (f" — ano {cur_year}." if cur_year else "."))
    if cur is not None:
        tip += f" Respondentes: {format_int(cur.get('respondents'))}."
    if len(obs) > 1:
        parts = [f"{o.get('year')}: {_fmt(o.get('today'), indicator)}"
                 for o in obs]
        tip += " Por ano — " + " • ".join(parts) + "."
        tip += (f" Comparado a 4 semanas: "
                f"{_COMP_GLYPH.get(cur.get('comparison'), '=') if cur else '='}"
                f" (Hoje vs Há 4 semanas).")
    if unit:
        tip += f" Unidade: {unit}."
    return kpi(f"{indicator} — {cur_year}" if cur_year else indicator,
               value, tip)


def _indicator_sections(indicator: str, obs: list[dict[str, Any]],
                        years: list[int]) -> list[dict[str, Any]]:
    """Chart (3 windows × years, grouped bars) + table for one indicator.

    Mirrors the static's per-indicator tab: one grouped bar chart + one
    sortable table — now nested inside its themed subtab.
    """
    sections: list[dict[str, Any]] = []
    labels = [str(o.get("year")) for o in obs] or [str(y) for y in years]

    # ── grouped bar chart: x = years, datasets = time windows ───────────────
    datasets = []
    for field, label in _WINDOWS:
        datasets.append({
            "label": label,
            "data": [o.get(field) for o in obs],
            "backgroundColor": _WINDOW_COLORS[field],
        })
    unit = _UNIT.get(indicator, "")
    options: dict[str, Any] = {
        "scales": {"y": {"beginAtZero": False}},
    }
    if unit:
        options["scales"]["y"]["title"] = {"display": True, "text": unit}
    sections.append(chart_section(
        f"Evolução das expectativas — {indicator}",
        {
            "type": "bar",
            "data": {"labels": labels, "datasets": datasets},
            "options": options,
        },
        description=(
            f"Como as expectativas para {indicator} variam entre os anos "
            f"({', '.join(labels)}) e entre as três janelas de tempo "
            "(Há 4 semanas, 1 sem, Hoje). Cada grupo de barras representa "
            "um ano; cada cor, uma janela de tempo."
        ),
    ))

    # ── per-year table ──────────────────────────────────────────────────────
    rows: list[list[Any]] = []
    for o in obs:
        rows.append([
            str(o.get("year", "")),
            _fmt(o.get("four_weeks_ago"), indicator),
            _fmt(o.get("one_week_ago"), indicator),
            _fmt(o.get("today"), indicator),
            _COMP_GLYPH.get(o.get("comparison"), "="),
            format_int(o.get("respondents")),
        ])
    tbl = table_section(
        f"{indicator} — por ano",
        ["Ano", "Há 4 semanas", "1 sem", "Hoje", "Comp.", "Resp."],
        rows,
        description=(
            f"Valores para {indicator} em cada ano. A coluna 'Comp.' "
            "compara 'Hoje' com 'Há 4 semanas' (▲ subiu, ▼ caiu, "
            "= estável). Clique no cabeçalho para ordenar."
        ),
    )
    tbl["sortable"] = True
    sections.append(tbl)
    return sections


# ── service ─────────────────────────────────────────────────────────────────
class FocusService:
    """Mercado page / Focus family — 7 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """O que o mercado projeta — KPIs + o Boletim por ano.

        Landing subtab: only what is GENERAL (the static's Focus tab).
        The 4 year subtabs become 4 stacked tables (macro:juros stacks 5
        monthly tables the same way); the specific per-indicator views
        live in their own subtabs — the note under each table points
        there.
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        obs = snap["observations"]
        years: list[int] = snap["years"]
        ref = snap["ref_date"]

        kpis = [
            kpi("Data de referência", _fmt_date(ref) or "-",
                "Data do boletim sincronizado (o Focus é semanal — a DDM "
                "não publica a data da rodada na página, a data de "
                "sincronização é o proxy mais próximo)."),
            kpi("Anos cobertos", format_int(len(years)),
                f"Anos de referência projetados: "
                f"{', '.join(str(y) for y in years)}."),
            kpi("Indicadores",
                format_int(snap.get("indicator_count")
                           or len({o.get("indicator") for o in obs})),
                "Indicadores acompanhados pelo Boletim Focus."),
            kpi("Observações", format_int(snap.get("row_count") or len(obs)),
                "Total de observações no boletim (anos × indicadores)."),
        ]

        sections: list[dict[str, Any]] = []
        for year in years:
            year_obs = [o for o in obs if o.get("year") == year]
            if not year_obs:
                continue
            rows: list[list[Any]] = []
            for o in year_obs:   # snapshot is indicator ASC within a year
                ind = o.get("indicator", "")
                rows.append([
                    ind,
                    _fmt(o.get("four_weeks_ago"), ind),
                    _fmt(o.get("one_week_ago"), ind),
                    _fmt(o.get("today"), ind),
                    _COMP_GLYPH.get(o.get("comparison"), "="),
                    format_int(o.get("respondents")),
                ])
            tbl = table_section(
                f"Boletim Focus — {year}",
                ["Indicador", "Há 4 semanas", "1 sem", "Hoje", "Comp.",
                 "Resp."],
                rows,
                description=(
                    f"Boletim Focus para o ano {year}. Cada linha mostra um "
                    "indicador com os valores 'Há 4 semanas', '1 sem' e "
                    "'Hoje', além da comparação (Comp.) e do número de "
                    "respondentes (Resp.). Clique no cabeçalho para ordenar."
                ),
                note=("Evolução por indicador (todos os anos, com gráficos) "
                      "nas subabas: Inflação, Atividade, Juros, Câmbio, "
                      "Setor Externo e Fiscal."),
            )
            tbl["sortable"] = True
            sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── themed indicator subtabs (6) ────────────────────────────────────────
    def _group_subtab(self, group: str) -> dict[str, Any]:
        """One themed subtab: KPI per indicator + chart + table each."""
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        obs = snap["observations"]
        years: list[int] = snap["years"]
        indicators = _GROUPS[group]

        kpis: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        found_any = False
        for ind in indicators:
            ind_obs = _by_indicator(obs, ind)
            if not ind_obs:
                # Per-indicator degradation: an empty note-table where the
                # indicator's sections would be (macro _err_note pattern).
                sections.append(table_section(
                    ind, ["Ano", "Há 4 semanas", "1 sem", "Hoje", "Comp.",
                          "Resp."], [],
                    description=(f"Sem dados para o indicador '{ind}' no "
                                 "boletim sincronizado."),
                ))
                continue
            found_any = True
            kpis.append(_kpi_for(ind_obs, ind, years))
            sections.extend(_indicator_sections(ind, ind_obs, years))

        if not found_any:
            return error_payload(
                "", "Nenhum indicador deste grupo consta no boletim "
                    "sincronizado — sincronize a fonte ddm-focus na "
                    "página Sincronização.")

        return {"status": "ok", "kpis": kpis, "sections": sections}

    def inflacao(self) -> dict[str, Any]:
        """Expectativas de preços — IPCA, IPCA Administrados, IGP-M."""
        return self._group_subtab("inflacao")

    def atividade(self) -> dict[str, Any]:
        """Crescimento — PIB Total."""
        return self._group_subtab("atividade")

    def juros(self) -> dict[str, Any]:
        """Taxas — Selic."""
        return self._group_subtab("juros")

    def cambio(self) -> dict[str, Any]:
        """Dólar — Câmbio."""
        return self._group_subtab("cambio")

    def externo(self) -> dict[str, Any]:
        """Contas externas — Conta corrente, Balança, Investimento direto."""
        return self._group_subtab("externo")

    def fiscal(self) -> dict[str, Any]:
        """Contas públicas — Dívida líquida, Primário, Nominal."""
        return self._group_subtab("fiscal")
