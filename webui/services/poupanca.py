"""webui/services/poupanca.py — Mercado page / Poupança family data service (DDM).

[v1.23] The Poupança family of the ``/webui/mercado`` page — the Brazilian
savings-account monthly yield (``ddm-poupanca``
source, ``memory_db/ddm/poupanca.db``). Seventh DDM family (focus v1.12,
fluxo v1.13, índices v1.14, inflação v1.15, juros v1.16, ações v1.17,
proventos v1.18) — placed BETWEEN Juros and Ações: the caderneta is renda
fixa, it reads right after the rates that drive it (the poupança rule is
0,5% a.m. + TR while Selic > 8,5% a.a., 70% da Selic + TR below) and
before the equity families.

Data model (the catalog's): the source page carries ONLY the monthly
matrix — the history is DERIVED at fetch time (fetcher
flatten_matrix_to_observations): ``month_value`` (rendimento % do mês),
``acumulado_no_ano`` (YTD SUM), ``acumulado_12m`` (rolling 12m SUM).
Poupança accumulates by SUM like inflation (the monthly yield is already
a return), NOT by average like juros.

Two subtabs (the family pattern — reference: the static
``poupanca_dashboard.html``, its gaps fixed per the v1.8–v1.18 spirit):

  overview → "a poupança paga?"        (the comparison the static never
              drew: Poupança × IPCA — does the caderneta beat inflation?
              — × CDI — the opportunity cost of leaving money in it.
              Monthly + 12m charts + the per-month real-yield table with
              the Poupança − IPCA difference column (negatives render
              red — the months the savings account lost purchasing
              power). Degrades to poupança-only when ddm-inflation /
              ddm-juros aren't synced — every missing series is named.)
  poupanca → "como a caderneta se move?"  (the inflação/juros per-index
              pattern: 3 KPIs + a evolução mensal — rendimento (cheia),
              acumulado no ano (tracejada, reseta em janeiro), acumulado
              12m (pontilhada) — + a matriz ano × mês em heatmap ANTES do
              histórico completo, que vem RECOLHIDO ([v1.23] the new
              convention) — the static's Histórico + Matriz subtabs
              merged into ONE, reordered)

Improvements over the static dashboard:
  - The static's single Poupanca tab answered only "quanto rendeu?" —
    the overview answers the question every poupança owner actually has:
    "deveria estar aqui?" (vs IPCA, vs CDI).
  - The matrix gains the final "Ano" column (sequential white→blue) —
    the source page has none, but the DB carries acumulado_no_ano and
    poupança accumulates by SUM exactly like the inflation family (the
    juros family's no-Ano rule is about RATES, not returns).
  - The per-index subtab follows the v1.23 convention: matrix BEFORE the
    Histórico mensal, the table COLLAPSED (the year-at-a-glance read
    leads; the row-by-row ledger opens on demand).
  - The 12m CDI comparison compounds the annual rate monthly
    ((1+r)^(1/12) — 21 of the 252 business days, 252 = 12×21), so the
    three 12m lines are the same kind of number (a 12-month return);
    the juros family's media_12m is an average of % a.a. rates and would
    read ~13 next to the poupança's ~8 on a chart — same axis, different
    units, the classic trap.

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker. The
adapters registry dispatches these through the v1.11 ticker-less path
and the generic endpoint ``GET /api/webui/mercado/sections/{key}``
serves them; all subtabs render through the generic renderer
(loadPoupancaSubtab → valKpisHtml + valSectionsHtml + mountValCharts in
app.js).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.ddm.poupanca.query_engine`` (memory_db/ddm/
    poupanca.db — poupanca_observations: 1 slug × ~176 monthly rows,
    2012-05 to date; month_value / acumulado_no_ano / acumulado_12m)
  - the overview's comparisons read the inflação/juros engines
    (ddm-inflation for IPCA, ddm-juros for CDI) — both optional,
    missing sources degrade gracefully and get named.

Formatting = the skill's helpers (``skills/ddm/poupanca/helpers.py`` —
``format_pct`` "0,62%", ``_heat_color`` the diverging red→white→green
matrix cells; the Ano column reuses the inflação helper's sequential
scheme — pure color math, no forked numerics).

Data conventions (v1.8 fix1 / v1.9–v1.23 lineage):
  - Table months "nov/2026" (sortable — _valSortKey parses that form).
  - Chart labels ship ISO "YYYY-MM" on purpose — renderValChart formats
    month axes + tooltips client-side since v1.15 and the range bar
    slices the ISO strings lexicographically.
  - Every number is a PRE-FORMATTED PT-BR string — the client only
    colorizes (negative red, % green).
  - Degradation: missing/empty poupanca.db → PT-BR ``_error`` naming
    the ``ddm-poupanca`` source exactly as the Sincronização page lists
    it (DDM — poupança).
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
from data_sources.ddm.poupanca.query_engine import (
    poupanca_history as _poupanca_history,
)
from data_sources.ddm.inflation.query_engine import (
    index_history as _index_history,
)
from data_sources.ddm.juros.query_engine import (
    juros_history as _juros_history,
)

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.ddm.poupanca.helpers import (
    format_pct as _pct,              # "0,62%" / "-" for None
    _heat_color as _heat_color,      # matrix cell {text, bg, color}
)
# the Ano column's sequential white→blue — the inflação helper's scheme
# (pure color math; the poupança helper only carries the diverging one)
from skills.ddm.inflation.helpers import _heat_color as _heat_seq

_ERR = ("Poupança indisponível — sincronize a fonte "
        "ddm-poupanca (DDM — poupança) na página "
        "Sincronização.")

# [skill pattern] The static dashboard's palette — rendimento emerald
# (#10b981), the lighter 300-shade for the dashed "Acumulado no ano"
# (#6ee7b7) and slate for the dotted 12m line (#94a3b8).
_C_POUP = "#10b981"      # emerald — the rendimento line
_C_ANO = "#6ee7b7"       # light emerald — the dashed YTD line
_C_12M = "#94a3b8"       # slate — the dotted 12m line (skill pattern)
_C_IPCA = "#f59e0b"      # amber — the inflação family's IPCA color
_C_CDI = "#a855f7"       # violet — CDI in the comparison charts

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


def _poupanca_series() -> dict[str, Any] | None:
    """poupanca_history() normalized; None on any failure/no data."""
    try:
        res = _poupanca_history(slug="poupanca", limit=0)
    except Exception:
        return None
    if res.get("status") != "ok":
        return None
    obs = [o for o in res.get("observations", []) if o.get("ref_date")]
    return {"observations": obs} if obs else None


def _opt_series(history: Any, slug: str) -> dict[str, Any] | None:
    """An OPTIONAL comparison series (IPCA via inflation, CDI via juros).

    The overview degrades to poupança-only when these aren't synced —
    None on any failure, never a raise (each missing source gets named
    in the section descriptions instead).
    """
    try:
        res = history(slug=slug, limit=0)
    except Exception:
        return None
    if res.get("status") != "ok":
        return None
    obs = [o for o in res.get("observations", []) if o.get("ref_date")]
    return {"observations": obs} if obs else None


def _cdi_12m(observations: list[dict[str, Any]]) -> dict[str, float]:
    """Rolling 12m compounded CDI (%) from the monthly % a.a. series.

    Each month contributes (1 + r/100)**(1/12) — 21 of the 252 business
    days (252 = 12×21, the standard annual→monthly conversion). The
    12-month product minus 1, in %, is the same KIND of number as the
    poupança/IPCA acumulado 12m (a 12-month return) — the juros family's
    media_12m is an average of annual-rate levels and would not belong
    on the same axis. Months with any missing value in their window get
    no reading (honest gap, no silent partial product).
    """
    vals = [(o.get("ref_date"), o.get("month_value"))
            for o in observations if len(str(o.get("ref_date") or "")) == 7]
    out: dict[str, float] = {}
    for i in range(11, len(vals)):
        window = vals[i - 11:i + 1]
        if any(v is None for _, v in window):
            continue
        prod = 1.0
        for _, v in window:
            prod *= (1.0 + float(v) / 100.0) ** (1.0 / 12.0)
        out[vals[i][0]] = (prod - 1.0) * 100.0
    return out


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
    """Line chart over ISO YYYY-MM labels + the client-side range bar."""
    cd: dict[str, Any] = {
        "type": "line",
        "data": {"labels": labels, "datasets": datasets},
        "options": {"scales": {"y": {"title": {"display": True,
                                               "text": y_title}}}},
    }
    sec = chart_section(title, cd, description=description)
    sec["price_range_selector"] = True   # client-side range bar
    return sec


def _by_date(observations: list[dict[str, Any]], field: str,
             months: list[str]) -> list[Any]:
    """One series aligned to the shared x axis (None where absent)."""
    m = {o["ref_date"]: o.get(field) for o in observations}
    return [m.get(d) for d in months]


def _union_months(*series: list[dict[str, Any]] | None) -> list[str]:
    """Union of every series' months, ASC — one shared x axis."""
    out: list[str] = []
    seen: set[str] = set()
    for s in series:
        if not s:
            continue
        for o in s:
            d = o.get("ref_date")
            if d and d not in seen:
                seen.add(d)
                out.append(d)
    out.sort()
    return out


def _pp(v: float | None) -> str:
    """Signed PT-BR percentage-point diff: +0,32 / -0,05 ('-' for None).

    Plain ASCII signs on purpose — the client's valNumHtml colors a
    leading '-' red (the months the poupança LOST to the IPCA glow).
    """
    if v is None:
        return "-"
    try:
        return f"{v:+.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "-"


def _matrix_rows(observations: list[dict[str, Any]]) -> list[list[Any]]:
    """Year × month matrix from the DB series (DESC by year, newest first).

    Jan–Dez cells = month_value (the rendimento of that month — the
    poupança helper's diverging red→white→green). The final "Ano" cell =
    the year's acumulado_no_ano (sequential white→blue, the inflação
    matrix's convention — poupança accumulates by SUM exactly like the
    price indices, and the DB carries what the source page doesn't).
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
        if o.get("acumulado_no_ano") is not None:
            year_acum[y] = o["acumulado_no_ano"]  # last one wins (ASC)

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
            out.append(_heat_color(row.get(mm), m_min, m_max))
        out.append(_heat_seq(year_acum.get(y), a_min, a_max, "sequential"))
        rows.append(out)
    return rows


# ── service ─────────────────────────────────────────────────────────────────
class PoupancaService:
    """Mercado page / Poupança family — 2 subtab payloads (FLAT, no ticker)."""

    # ── KPIs (shared shape — the family's single index) ────────────────────
    @staticmethod
    def _kpis(last: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            kpi("Poupança — mês", _pct(last.get("month_value")),
                f"Rendimento de {_br_month(last.get('ref_date'))} · "
                f"acumulado no ano: {_pct(last.get('acumulado_no_ano'))}. "
                "A caderneta rende 0,5% ao mês + TR enquanto a Selic "
                "estiver acima de 8,5% a.a., ou 70% da Selic + TR abaixo "
                "disso."),
            kpi("Poupança — ano", _pct(last.get("acumulado_no_ano")),
                f"Acumulado no ano corrente (jan a "
                f"{_br_month(last.get('ref_date'))}) — a soma dos "
                "rendimentos mensais."),
            kpi("Poupança — 12m", _pct(last.get("acumulado_12m")),
                "Soma dos rendimentos dos últimos 12 meses (janela "
                "móvel) — o retorno anualizado simples da caderneta."),
        ]

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """A poupança paga — a caderneta contra o IPCA e o CDI.

        Landing subtab: the COMPARISON the static never drew (its single
        tab answered only "quanto rendeu?"). Monthly yield vs the month's
        IPCA (the real-yield question) and the 12m returns side by side
        with the compounded CDI (the opportunity-cost question), plus the
        per-month table with the Poupança − IPCA difference column.
        """
        s = _poupanca_series()
        if s is None:
            return error_payload("", _ERR)

        obs = s["observations"]
        last = _last(obs)
        kpis = self._kpis(last)

        # OPTIONAL comparison series — each degrades gracefully.
        ipca = _opt_series(_index_history, "ipca")
        cdi = _opt_series(_juros_history, "cdi")
        cdi12 = _cdi_12m(cdi["observations"]) if cdi else {}

        # ── Chart 1 — monthly: Poupança × IPCA (the real-yield read) ──
        months1 = _union_months(obs, ipca["observations"] if ipca else None)
        ds1 = [_line_ds("Poupança (%)",
                        _by_date(obs, "month_value", months1), _C_POUP)]
        if ipca:
            ds1.append(_line_ds("IPCA (%)",
                                _by_date(ipca["observations"],
                                         "month_value", months1), _C_IPCA))
        desc1 = (
            "O rendimento mensal da caderneta contra a inflação do mês "
            "— a poupança só constrói poder de compra nos meses em que a "
            "linha verde fica acima da âmbar."
            + ("" if ipca else " O IPCA não está sincronizado — "
               "sincronize a fonte ddm-inflation (DDM — índices de "
               "preços) para o comparativo.")
            + " Use a barra de período para filtrar."
        )
        sections: list[dict[str, Any]] = [
            _month_chart("Rendimento mensal — Poupança × IPCA", ds1, months1,
                         y_title="% (mês)", description=desc1),
        ]

        # ── Chart 2 — 12m returns: Poupança × IPCA × CDI ──
        months2 = _union_months(obs, ipca["observations"] if ipca else None,
                                cdi["observations"] if cdi else None)
        ds2 = [_line_ds("Poupança 12m (%)",
                        _by_date(obs, "acumulado_12m", months2), _C_POUP)]
        if ipca:
            ds2.append(_line_ds("IPCA 12m (%)",
                                _by_date(ipca["observations"],
                                         "acumulado_12m", months2), _C_IPCA))
        if cdi12:
            ds2.append(_line_ds("CDI 12m (%)",
                                [cdi12.get(d) for d in months2], _C_CDI))
        missing2 = []
        if not ipca:
            missing2.append("ddm-inflation (IPCA)")
        if not cdi12:
            missing2.append("ddm-juros (CDI)")
        desc2 = (
            "O retorno dos últimos 12 meses, janela móvel: a poupança e "
            "o IPCA somam os rendimentos mês a mês (a convenção das "
            "fontes); o CDI é composto a partir da taxa a.a. de cada mês "
            "(1/12 do ano = 21 dos 252 dias úteis). Abaixo do IPCA a "
            "caderneta perde poder de compra; abaixo do CDI, perde para "
            "a renda fixa pós-fixada."
            + ("" if not missing2 else
               " Sem sincronizar: " + " e ".join(missing2) + ".")
        )
        sections.append(_month_chart(
            "Acumulado 12 meses — Poupança × IPCA × CDI", ds2, months2,
            y_title="% (acum. 12m)", description=desc2))

        # ── Comparison table — newest first, last 24 months ──
        poup_map = {o["ref_date"]: o for o in obs}
        ipca_map = ({o["ref_date"]: o for o in ipca["observations"]}
                    if ipca else {})
        rows = []
        for ym in reversed([o["ref_date"] for o in obs][-_MONTHS_TABLE:]):
            p = poup_map.get(ym, {})
            i = ipca_map.get(ym)
            row: list[Any] = [_br_month(ym)]
            # Poupança first (the table's subject)…
            row.append(_pct(p.get("month_value")))
            # …then the IPCA + difference columns when the source has it.
            if ipca_map:
                if i:
                    row.append(_pct(i.get("month_value")))
                    pv, iv = p.get("month_value"), i.get("month_value")
                    row.append(_pp(pv - iv
                                   if pv is not None and iv is not None
                                   else None))
                else:
                    row.extend(["-", "-"])
            tips = []
            if p.get("acumulado_12m") is not None:
                tips.append(f"Poupança 12m: {_pct(p.get('acumulado_12m'))}")
            if i and i.get("acumulado_12m") is not None:
                tips.append(f"IPCA 12m: {_pct(i.get('acumulado_12m'))}")
            if tips:
                row[0] = {"text": _br_month(ym),
                          "tooltip": f"Acumulado 12m — {' · '.join(tips)}."}
            rows.append(row)

        columns = ["Mês", "Poupança (%)"]
        if ipca_map:
            columns += ["IPCA (%)", "Poupança − IPCA (p.p.)"]
        tbl = table_section(
            "Poupança × IPCA — mês a mês",
            columns,
            rows,
            description=(
                "O rendimento da caderneta e a inflação de cada mês, "
                f"lado a lado (mais recentes primeiro — últimos "
                f"{_MONTHS_TABLE} meses). A coluna de diferença em "
                "pontos percentuais diz se o mês construiu (+) ou "
                "consumiu (−, em vermelho) poder de compra. O ⓘ de cada "
                "mês carrega os acumulados 12m."
            ),
            note=(
                "O histórico completo da caderneta e a matriz ano × mês "
                "estão na subaba Poupança."
                + ("" if ipca_map else
                   " Sincronize a fonte ddm-inflation (DDM — índices de "
                   "preços) para as colunas do IPCA.")),
        )
        tbl["sortable"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Poupança (the index view) ───────────────────────────────────────────
    def poupanca(self) -> dict[str, Any]:
        """Como a caderneta se move — evolução + matriz + histórico.

        The static's Historico + Matriz subtabs merged into ONE subtab
        (its gap: reading the evolution and the matrix required a subtab
        flip), with the v1.23 convention: the matrix BEFORE the
        Histórico mensal, the table COLLAPSED. The evolução chart keeps
        the static's 3-line design: rendimento (cheia), acumulado no ano
        (tracejada, reseta em janeiro), acumulado 12m (pontilhada).
        """
        s = _poupanca_series()
        if s is None:
            return error_payload("", _ERR)

        obs = s["observations"]
        last = _last(obs)
        labels = [o["ref_date"] for o in obs]
        first_year = labels[0][:4] if labels else ""
        last_year = labels[-1][:4] if labels else ""

        kpis = self._kpis(last)

        sections: list[dict[str, Any]] = [
            _month_chart(
                "Evolução mensal",
                [
                    _line_ds("Rendimento no mês (%)",
                             [o.get("month_value") for o in obs], _C_POUP),
                    _line_ds("Acumulado no ano (%)",
                             [o.get("acumulado_no_ano") for o in obs],
                             _C_ANO, dash=[5, 5]),
                    _line_ds("Acumulado 12 meses (%)",
                             [o.get("acumulado_12m") for o in obs],
                             _C_12M, dash=[2, 4]),
                ],
                labels,
                y_title="% (rendimento)",
                description=(
                    "Rendimento mensal (linha cheia), acumulado no ano "
                    "(tracejada — reseta em 1º de janeiro) e acumulado "
                    "12 meses (pontilhada) da poupança. Todo o histórico "
                    f"disponível ({first_year} a {last_year}); use a "
                    "barra de período para filtrar."
                ),
            ),
        ]

        # [v1.23] The matrix comes FIRST — the year-at-a-glance read
        # leads, and the full Histórico mensal follows COLLAPSED (the
        # same numbers, one row per month; the summary carries the row
        # count — opens on demand).
        matrix = _matrix_rows(obs)
        if matrix:
            sections.append(heatmap_section(
                "Matriz ano × mês",
                ["Ano", *_MONTH_LABELS, "Ano"],
                matrix,
                description=(
                    "Matriz ano × mês do rendimento mensal (%). A coluna "
                    "final 'Ano' é o acumulado no ano — calculado do "
                    "histórico (a página da fonte não traz essa coluna; "
                    "a poupança acumula por soma exatamente como os "
                    "índices de preços). Cores: vermelho=rendimento "
                    "baixo, branco=ponto médio, verde=alto (mensal); "
                    "branco→azul (anual)."
                ),
            ))

        # Full history table — newest first (static convention), sortable,
        # COLLAPSED (v1.23: the matrix above already answers the year
        # reads; the row-by-row ledger opens on demand).
        rows = [
            [_br_month(o["ref_date"]),
             _pct(o.get("month_value")),
             _pct(o.get("acumulado_no_ano")),
             _pct(o.get("acumulado_12m"))]
            for o in reversed(obs)
        ]
        tbl = table_section(
            "Histórico mensal",
            ["Mês", "Rendimento (%)", "Acumulado no ano (%)",
             "Acumulado 12m (%)"],
            rows,
            description=(
                "Todas as observações, derivadas da matriz mensal da "
                "fonte (mais recentes primeiro). Clique no cabeçalho "
                "para ordenar — a coluna Mês ordena cronologicamente."
            ),
            note=(f"{len(rows)} observações sincronizadas — a matriz "
                  "ano × mês acima resume este histórico em heatmap."),
        )
        tbl["sortable"] = True
        tbl["collapsed"] = True
        sections.append(tbl)

        return {"status": "ok", "kpis": kpis, "sections": sections}
