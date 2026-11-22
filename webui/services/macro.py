"""webui/services/macro.py — Macro page data service (BCB SGS + Focus).

[v1.11] The macro-economic view for the ``/webui/macro`` page — a
reorganized take on the static ``macro_dashboard.html`` reference (built by
skills/bcb/macro/modes/dashboard.py, 8 flat tabs). Per the v1.11 design the
LANDING subtab carries only what is general — the static dashboard's
"Indicadores Atuais" table + its 4 header KPIs — and every specific view
becomes its own lazy subtab, exactly like the company tabs since v1.8:

  overview       → "where does the economy stand?"   (4 KPIs + the
                    Indicadores Atuais table — 10 current series)
  juros          → "what do rates do?"               (Selic/CDI/Meta Copom
                    combined chart + TR + Selic acumulada + monthly tables)
  inflacao       → "what does inflation do?"         (IPCA vs IGP-M mensal +
                    acumulado 12m charts + tables)
  cambio         → "where is the BRL?"               (USD/BRL ptax diária +
                    média mensal + stats)
  atividade      → "how is the activity?"            (PIB nominal trimestral
                    + salário mínimo)
  retorno_real   → "what does money yield?"          (Fisher equation —
                    Selic vs IPCA acumulado 12m)
  focus          → "what does the market expect?"    (Focus mediana ± faixa
                    min/max para IPCA/Selic/Câmbio)
  curva          → "which rate path is priced in?"   (Curva de juros
                    esperada — Selic Focus por ano de referência)

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker — macro is
market-wide. The adapters registry dispatches these through the ticker-less
path (``takes_ticker=False`` — see webui/adapters/registry.py) and the
generic endpoint ``GET /api/webui/macro/sections/{key}`` serves them; all
subtabs render through the generic renderer (loadMacroSubtab → valKpisHtml
+ valSectionsHtml + mountValCharts in app.js).

Data layer = the SAME query engines the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.bcb.sgs.query_engine``  (sgs.db  — Selic/CDI/TR/Meta/
    IPCA/IGP-M/USD-BRL/PIB/salário)
  - ``data_sources.bcb.focus.query_engine`` (focus.db — Olinda expectations)

Data conventions (v1.8 fix1 / v1.9 / v1.10 lineage):
  - Every date the user READS (table cells) is dd/mm/yyyy via ``_fmt_date``;
    months read "jun/2026" via ``_br_month`` (sortable — _valSortKey parses
    that form). Chart labels ship ISO on purpose — renderValChart detects
    all-ISO x labels and formats ticks + tooltips client-side.
  - Every number is a PRE-FORMATTED PT-BR string (comma decimals) — the
    client only colorizes (negative red, % green/red — Fisher real rates
    get the sign coloring for free).
  - History charts carry ``price_range_selector`` — the Tudo/10A/…/1M bar
    filters client-side from chart_data itself (v1.7.2). The Curva chart
    (years on x) deliberately does NOT — it is forward-looking, not a
    historical range.

Improvements over the static dashboard (same reorganization spirit as
v1.8–v1.10 — the static gaps get fixed, not copied):
  - Juros: the static shipped 5 near-duplicate single-series charts; here
    Selic + CDI + Meta Copom share ONE % a.a. chart (they only differ by
    ~10 bps), leaving TR and Selic-acumulada as their own charts. Monthly
    tables show the ANNUALIZED month-end rate (the static showed raw daily
    % a.d. — "0,050788%" reads as noise).
  - Inflação: one chart per QUESTION (variação mensal, acumulado 12m) with
    IPCA + IGP-M together, not 4 charts per series.
  - Retorno Real: the real-rate line is joined to a monthly IPCA step (the
    static chart shipped only the final Fisher number as KPI + a Selic-only
    daily chart duplicated from Juros).
  - Degradation is source-scoped with PT-BR ``_error`` payloads naming the
    sync source (``sgs`` / ``focus``) exactly as the Sincronização page
    lists it — a missing DB reads as an actionable message, not a stack
    trace.
"""
from __future__ import annotations

import sys
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
from data_sources.bcb.sgs.query_engine import (
    last_value as _sgs_last,
    series as _sgs_series,
)
from data_sources.bcb.focus.query_engine import (
    expectations as _focus_expectations,
)

from tools.report_ops.formats import fmt_brl, fmt_int, fmt_num

# ── series codes (mirror skills/bcb/macro/modes/dashboard.py) ───────────────
SELIC_DAILY = 11     # % a.d. (base 252)
CDI_DAILY = 12       # % a.d. (base 252)
TR_DAILY = 226       # %
META_COPOM = 432     # % a.a.
SELIC_ACUM = 4389    # % a.a. (acumulada no mês, base 252)
IPCA_MENSAL = 433    # % mensal
IGPM_MENSAL = 189    # % mensal
USD_BRL = 1          # R$ (ptax venda)
PIB_NOMINAL = 4380   # R$ milhões (trimestral — IBGE/BCB; unit fix, see catalog)
SALARIO_MIN = 1619   # R$ (mensal)

# ── windows (static dashboard v1.6 defaults — full synced history ~5y) ──────
_DAYS = 3650          # daily-series row cap
_MONTHS = 60          # monthly-series row cap (rolling computations)
_MONTHS_TABLE = 24    # monthly table rows shown
_FX_TABLE = 24        # câmbio monthly-average table rows

# ── palette (same accents as the skill's static report) ─────────────────────
_C_SELIC = "#0d9488"   # teal    — Selic / juros
_C_CDI = "#3b82f6"     # blue    — CDI
_C_META = "#f59e0b"    # amber   — Meta Copom / inflação
_C_IPCA = "#f59e0b"    # amber   — IPCA
_C_IGPM = "#8b5cf6"    # violet  — IGP-M
_C_FX = "#3b82f6"      # blue    — câmbio
_C_MAX = "#ef4444"     # red     — máximo
_C_MIN = "#22c55e"     # green   — mínimo
_C_TR = "#94a3b8"      # slate   — TR
_C_PIB = "#0d9488"     # teal    — atividade
_C_SAL = "#3b82f6"     # blue    — salário
_C_REAL = "#0d9488"    # teal    — retorno real

# [v1.9] ISO date detector — same convention as options.py/insiders.py.
import re as _re

_ISO_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")

_BR_MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez")


# ── formatting helpers (PT-BR pre-formatted strings — client only colors) ───
def _fmt_date(s: Any) -> Any:
    """ISO "2026-12-31" → "31/12/2026" (padrão brasileiro).

    Non-ISO values pass through untouched so degraded "-" survives. Chart
    labels are the deliberate exception — they ship ISO and the client
    formats axis ticks + tooltip titles (v1.8 fix1 convention).
    """
    if isinstance(s, str) and _ISO_DATE_RE.match(s):
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def _br_month(s: Any) -> Any:
    """'2026-06' → 'jun/2026' (short PT-BR month, sortable by _valSortKey)."""
    if isinstance(s, str) and len(s) >= 7 and s[4] == "-":
        try:
            m = int(s[5:7])
            if 1 <= m <= 12:
                return f"{_BR_MONTHS[m - 1]}/{s[:4]}"
        except ValueError:
            pass
    return s


def _pct(v: Any, dec: int = 2) -> str:
    """12.7989... → '12,80%'. None → '-'."""
    if v is None:
        return "-"
    return fmt_num(v, decimals=dec).replace("-", "-") + "%"


def _brl4(v: Any) -> str:
    """5.8889 → 'R$ 5,8889' (ptax 4-decimal convention)."""
    if v is None:
        return "-"
    return "R$ " + fmt_num(v, decimals=4)


def _brl2(v: Any) -> str:
    """1621.0 → 'R$ 1.621,00'."""
    if v is None:
        return "-"
    return "R$ " + fmt_num(v, decimals=2)


def _tri_br(v_milhoes: Any) -> str:
    """PIB em R$ milhões → compacto ('R$ 1,17 tri')."""
    if v_milhoes is None:
        return "-"
    return fmt_brl(float(v_milhoes) * 1_000_000.0, suffix=True)


def _annualize(daily_pct: float | None) -> float | None:
    """% a.d. → % a.a. (base 252)."""
    if daily_pct is None:
        return None
    return daily_pct * 252.0


def _observations(code: int, rows: int) -> list[dict[str, Any]]:
    """Query a series' observations; [] on any failure (degrades per-series)."""
    res = _sgs_series(code=code, days=rows)
    if res.get("status") != "ok":
        return []
    return res.get("observations", [])


def _last(code: int) -> dict[str, Any]:
    """last_value() dict (status/value/ref_date/unit) — never raises."""
    try:
        return _sgs_last(code=code)
    except Exception:
        return {"status": "error"}


def _err_note(label: str, error: str) -> dict[str, Any]:
    """Per-series degradation: an empty table whose note carries the error.

    The FLAT contract has no text section; an empty sortable table with the
    error in ``note`` renders inline exactly where the series would be.
    """
    return table_section(
        label, ["Data", "Valor"], [],
        description=f"Erro ao consultar: {error}",
    )


def _sgs_unavailable(res: dict[str, Any]) -> bool:
    return res.get("status") in ("not_synced", "error")


def _sgs_error_payload() -> dict[str, Any]:
    return error_payload(
        "", "Dados macroeconômicos indisponíveis — sincronize a fonte "
           "sgs (BCB — Sistema Gerenciador de Séries Temporais) na "
           "página Sincronização.")


def _focus_error_payload() -> dict[str, Any]:
    return error_payload(
        "", "Expectativas do mercado indisponíveis — sincronize a fonte "
           "focus (BCB Focus — Olinda OData) na página Sincronização.")


# ── chart helpers ────────────────────────────────────────────────────────────
def _line_ds(label: str, data: list[Any], color: str, *,
             dash: bool = False, width: int = 2,
             point_radius: int = 0) -> dict[str, Any]:
    """One line dataset (server styling is honored by renderValChart)."""
    ds: dict[str, Any] = {
        "label": label, "data": data,
        "borderColor": color, "backgroundColor": color,
        "borderWidth": width, "pointRadius": point_radius,
        "pointHoverRadius": 4, "tension": 0.25, "fill": False,
    }
    if dash:
        ds["borderDash"] = [4, 4]
        ds["borderWidth"] = 1
    return ds


def _history_chart(title: str, datasets: list[dict[str, Any]],
                   labels: list[str], y_title: str = "",
                   description: str = "") -> dict[str, Any]:
    """Line chart over ISO date labels + the client-side range bar."""
    options: dict[str, Any] = {}
    if y_title:
        options = {"scales": {"y": {"title": {"display": True,
                                              "text": y_title}}}}
    cd: dict[str, Any] = {
        "type": "line",
        "data": {"labels": labels, "datasets": datasets},
    }
    if options:
        cd["options"] = options
    sec = chart_section(title, cd, description=description)
    sec["price_range_selector"] = True   # v1.7.2 client-side range bar
    return sec


def _month_end_series(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Daily obs → last value per YYYY-MM (skill helpers.group_by_month)."""
    by_month: dict[str, float] = {}
    for o in observations:
        ref = o.get("ref_date", "")
        if len(ref) >= 7 and o.get("value") is not None:
            by_month[ref[:7]] = o["value"]   # last wins (obs are ASC)
    return [{"ref_date": k, "value": v} for k, v in sorted(by_month.items())]


def _rolling_12m(monthly: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Monthly obs → same-length list with rolling 12-month sum (skill
    helpers.accumulate_12m semantics — first 11 rows are None)."""
    out = []
    for i, row in enumerate(monthly):
        window = monthly[max(0, i - 11): i + 1]
        nums = [w.get("value") for w in window if w.get("value") is not None]
        out.append({"ref_date": row.get("ref_date", ""),
                    "value": row.get("value"),
                    "acum_12m": sum(nums) if len(nums) >= 12 else None})
    return out


def _monthly_avg(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Daily obs → per-YYYY-MM average (skill modes/fx semantics)."""
    buckets: dict[str, list[float]] = {}
    for o in daily:
        ref = o.get("ref_date", "")
        v = o.get("value")
        if len(ref) >= 7 and v is not None:
            buckets.setdefault(ref[:7], []).append(v)
    return [{"ref_date": f"{k}-01", "value": sum(v) / len(v)}
            for k, v in sorted(buckets.items())]


def _dedupe_focus(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedup by (data, data_referencia) keeping the most respondents
    (skill modes/expectations v1.7 logic — multiple survey rounds on the
    same day otherwise duplicate chart points and table rows)."""
    seen: dict[tuple, dict[str, Any]] = {}
    for o in observations:
        key = (o.get("data", ""), o.get("data_referencia", ""))
        cur = seen.get(key)
        if cur is None or (o.get("numero_respondentes") or 0) > \
                (cur.get("numero_respondentes") or 0):
            seen[key] = o
    return list(seen.values())


class MacroService:
    """Macro page data service — 8 subtab payloads (FLAT contract, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """Onde a economia está — KPIs + a tabela Indicadores Atuais.

        Landing subtab: only what is GENERAL (the static dashboard's Resumo
        tab). Every specific view lives in its own subtab — the note under
        the table points there.
        """
        selic = _last(SELIC_DAILY)
        cdi = _last(CDI_DAILY)
        meta = _last(META_COPOM)
        ipca = _last(IPCA_MENSAL)
        fx = _last(USD_BRL)

        # Rolling 12m acumulado for the IPCA/IGP-M rows.
        ipca_m = _observations(IPCA_MENSAL, _MONTHS)
        igpm_m = _observations(IGPM_MENSAL, _MONTHS)
        ipca_12m = _rolling_12m(ipca_m)[-1].get("acum_12m") if ipca_m else None
        igpm_12m = _rolling_12m(igpm_m)[-1].get("acum_12m") if igpm_m else None

        if _sgs_unavailable(selic) and _sgs_unavailable(ipca):
            return _sgs_error_payload()

        kpis: list[dict[str, Any]] = [
            kpi("Selic (anualizada)", _pct(_annualize(selic.get("value"))),
                "Taxa Selic diária anualizada (base 252). "
                f"Ref: {_fmt_date(selic.get('ref_date'))}."),
            kpi("CDI (anualizada)", _pct(_annualize(cdi.get("value"))),
                "CDI diário anualizado (base 252) — taxa das operações "
                "interbancárias DI. "
                f"Ref: {_fmt_date(cdi.get('ref_date'))}."),
            kpi("IPCA (mês)", _pct(ipca.get("value")),
                "Variação mensal do IPCA. "
                f"Acumulado 12m: {_pct(ipca_12m)}. "
                f"Ref: {_fmt_date(ipca.get('ref_date'))}."),
            kpi("USD/BRL (ptax)", _brl4(fx.get("value")),
                "Dólar venda — taxa ptax. "
                f"Ref: {_fmt_date(fx.get('ref_date'))}."),
        ]

        rows: list[list[Any]] = []
        for label, res, fmt in [
            ("Selic (anualizada)", selic, lambda v: _pct(_annualize(v))),
            ("Selic diária", selic, lambda v: _pct(v, 6)),
            ("CDI (anualizada)", cdi, lambda v: _pct(_annualize(v))),
            ("CDI diária", cdi, lambda v: _pct(v, 6)),
            ("Meta Selic (Copom)", meta, lambda v: _pct(v)),
            ("IPCA (mês)", ipca, lambda v: _pct(v)),
            # Synthetic rows for the computed acumulado 12m values —
            # "status": "ok" is REQUIRED (the loop's ok-check is what
            # decides value vs "-"; the None check below still degrades
            # when the rolling window has no data).
            ("IPCA (acumulado 12m)", {"status": "ok",
                                      "value": ipca_12m,
                                      "ref_date": ipca.get("ref_date")},
             lambda v: _pct(v)),
            ("IGP-M (mês)", _last(IGPM_MENSAL), lambda v: _pct(v)),
            ("IGP-M (acumulado 12m)", {"status": "ok",
                                       "value": igpm_12m,
                                       "ref_date": _last(IGPM_MENSAL).get("ref_date")},
             lambda v: _pct(v)),
            ("USD/BRL (ptax)", fx, _brl4),
            ("TR (Taxa Referencial)", _last(TR_DAILY), lambda v: _pct(v, 4)),
            ("Salário mínimo", _last(SALARIO_MIN), _brl2),
        ]:
            if res.get("status") == "ok" and res.get("value") is not None:
                rows.append([label, fmt(res["value"]),
                             _fmt_date(res.get("ref_date"))])
            else:
                rows.append([label, "-", "-"])

        sections = [
            table_section(
                "Indicadores Atuais",
                ["Indicador", "Valor", "Data Ref."],
                rows,
                description="Última observação de cada série — BCB SGS.",
                note=("Detalhes e histórico por indicador nas abas: "
                      "Juros, Inflação, Câmbio, Atividade, Retorno Real, "
                      "Focus e Curva de Juros."),
            ),
        ]
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Juros ───────────────────────────────────────────────────────────────
    def juros(self) -> dict[str, Any]:
        """O que fazem as taxas — Selic/CDI/Meta juntas + TR + acumulada.

        The static dashboard shipped 5 near-duplicate single-series charts;
        Selic, CDI and Meta Copom differ by ~10 bps, so they share ONE
        % a.a. chart. Monthly tables show the ANNUALIZED month-end rate
        (raw daily "% a.d." reads as noise).
        """
        selic = _sgs_series(code=SELIC_DAILY, days=_DAYS)
        if _sgs_unavailable(selic):
            return _sgs_error_payload()

        cdi = _sgs_series(code=CDI_DAILY, days=_DAYS)
        meta = _sgs_series(code=META_COPOM, days=_DAYS)
        tr = _sgs_series(code=TR_DAILY, days=_DAYS)
        acum = _sgs_series(code=SELIC_ACUM, days=_DAYS)

        s_obs = selic.get("observations", [])

        # KPIs — latest values (annualized where % a.d.).
        s_last, c_last = s_obs[-1] if s_obs else {}, \
            (cdi.get("observations") or [{}])[-1]
        m_last = (meta.get("observations") or [{}])[-1]
        t_last = (tr.get("observations") or [{}])[-1]
        a_last = (acum.get("observations") or [{}])[-1]
        kpis = [
            kpi("Selic (a.a.)", _pct(_annualize(s_last.get("value"))),
                "Selic diária anualizada (base 252). "
                f"Diária: {_pct(s_last.get('value'), 6)} · "
                f"ref: {_fmt_date(s_last.get('ref_date'))}."),
            kpi("CDI (a.a.)", _pct(_annualize(c_last.get("value"))),
                "CDI diário anualizado (base 252). "
                f"Ref: {_fmt_date(c_last.get('ref_date'))}."),
            kpi("Meta Selic (Copom)", _pct(m_last.get("value")),
                "Meta definida pelo Copom. "
                f"Ref: {_fmt_date(m_last.get('ref_date'))}."),
            kpi("TR", _pct(t_last.get("value"), 4),
                "Taxa Referencial — base da poupança e de contratos. "
                f"Ref: {_fmt_date(t_last.get('ref_date'))}."),
            kpi("Selic acumulada no mês (base 252)",
                _pct(a_last.get("value")),
                "Selic acumulada no mês, anualizada. "
                f"Ref: {_fmt_date(a_last.get('ref_date'))}."),
        ]

        sections: list[dict[str, Any]] = []

        # Chart 1 — the combined basic-rates chart (annualized).
        by_date_c = {o["ref_date"]: o.get("value")
                     for o in cdi.get("observations", [])}
        by_date_m = {o["ref_date"]: o.get("value")
                     for o in meta.get("observations", [])}
        labels = [o["ref_date"] for o in s_obs]
        sections.append(_history_chart(
            "Juros básicos — Selic vs CDI vs Meta Copom (% a.a.)",
            [
                _line_ds("Selic", [_annualize(o.get("value")) for o in s_obs],
                         _C_SELIC),
                _line_ds("CDI", [_annualize(by_date_c.get(d)) for d in labels],
                         _C_CDI),
                _line_ds("Meta Copom", [by_date_m.get(d) for d in labels],
                         _C_META, width=1),
            ],
            labels, y_title="% a.a.",
            description="Taxas diárias anualizadas (base 252); a Meta Copom "
                        "é a taxa-alvo (degraus).",
        ))

        # Chart 2 — TR.
        if tr.get("status") == "ok":
            t_obs = tr.get("observations", [])
            sections.append(_history_chart(
                "TR — Taxa Referencial (%)",
                [_line_ds("TR", [o.get("value") for o in t_obs], _C_TR)],
                [o["ref_date"] for o in t_obs], y_title="%",
                description="Base da poupança e de contratos indexados à TR.",
            ))
        else:
            sections.append(_err_note("TR", tr.get("error", "sem dados")))

        # Chart 3 — Selic acumulada no mês.
        if acum.get("status") == "ok":
            a_obs = acum.get("observations", [])
            sections.append(_history_chart(
                "Selic acumulada no mês (base 252) (% a.a.)",
                [_line_ds("Selic acumulada",
                          [o.get("value") for o in a_obs], _C_SELIC)],
                [o["ref_date"] for o in a_obs], y_title="% a.a.",
            ))
        else:
            sections.append(_err_note("Selic acumulada",
                                      acum.get("error", "sem dados")))

        # Monthly tables — annualized month-end for the % a.d. series.
        for code, res, label, annualize in [
            (SELIC_DAILY, selic, "Selic", True),
            (CDI_DAILY, cdi, "CDI", True),
            (META_COPOM, meta, "Meta Copom", False),
            (TR_DAILY, tr, "TR", False),
            (SELIC_ACUM, acum, "Selic acumulada (base 252)", False),
        ]:
            if res.get("status") != "ok":
                continue
            monthly = _month_end_series(res.get("observations", []))[
                -_MONTHS_TABLE:]
            monthly.reverse()   # newest first
            unit = "% a.a." if annualize else "%"
            rows = [[_br_month(m["ref_date"]),
                     _pct(_annualize(m["value"]) if annualize else m["value"])]
                    for m in monthly]
            sections.append(table_section(
                f"{label} — mensal (fim do mês)",
                ["Mês", f"Valor ({unit})"], rows,
                description="Última observação de cada mês"
                            + (" anualizada (base 252)." if annualize else "."),
            ))
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Inflação ────────────────────────────────────────────────────────────
    def inflacao(self) -> dict[str, Any]:
        """O que faz a inflação — IPCA e IGP-M, mensal e acumulado 12m."""
        ipca = _sgs_series(code=IPCA_MENSAL, days=_MONTHS)
        if _sgs_unavailable(ipca):
            return _sgs_error_payload()
        igpm = _sgs_series(code=IGPM_MENSAL, days=_MONTHS)

        i_obs = ipca.get("observations", [])
        g_obs = igpm.get("observations", []) if igpm.get("status") == "ok" else []
        i_enr = _rolling_12m(i_obs)
        g_enr = _rolling_12m(g_obs)
        i_last = i_enr[-1] if i_enr else {}
        g_last = g_enr[-1] if g_enr else {}

        kpis = [
            kpi("IPCA (mês)", _pct(i_last.get("value")),
                f"Ref: {_fmt_month(i_last.get('ref_date'))}. "
                f"Acumulado 12m: {_pct(i_last.get('acum_12m'))}."),
            kpi("IPCA (acumulado 12m)", _pct(i_last.get("acum_12m")),
                "Soma das variações mensais dos últimos 12 meses."),
            kpi("IGP-M (mês)", _pct(g_last.get("value")),
                f"Ref: {_fmt_month(g_last.get('ref_date'))}. "
                f"Acumulado 12m: {_pct(g_last.get('acum_12m'))}."),
            kpi("IGP-M (acumulado 12m)", _pct(g_last.get("acum_12m")),
                "Soma das variações mensais dos últimos 12 meses."),
        ]

        sections: list[dict[str, Any]] = []

        # Chart 1 — monthly variation, both indices together.
        labels = [o["ref_date"] for o in i_obs]
        g_map = {o["ref_date"]: o.get("value") for o in g_obs}
        sections.append(_history_chart(
            "IPCA vs IGP-M — variação mensal (%)",
            [
                _line_ds("IPCA", [o.get("value") for o in i_obs], _C_IPCA),
                _line_ds("IGP-M", [g_map.get(d) for d in labels], _C_IGPM),
            ],
            labels, y_title="%",
            description="Variação percentual mensal de cada índice.",
        ))

        # Chart 2 — rolling 12-month acumulado.
        sections.append(_history_chart(
            "IPCA vs IGP-M — acumulado 12 meses (%)",
            [
                _line_ds("IPCA 12m", [r.get("acum_12m") for r in i_enr],
                         _C_IPCA),
                _line_ds("IGP-M 12m", [r.get("acum_12m") for r in g_enr],
                         _C_IGPM),
            ],
            [r["ref_date"] for r in i_enr], y_title="%",
            description="Soma das variações dos últimos 12 meses (janela "
                        "móvel) — a leitura de inflação que o BCB acompanha "
                        "para a meta.",
        ))

        # Tables — monthly + acumulado side by side per index.
        for name, enr, color in [("IPCA", i_enr, _C_IPCA),
                                 ("IGP-M", g_enr, _C_IGPM)]:
            if not enr:
                sections.append(_err_note(
                    name, igpm.get("error", "sem dados") if name == "IGP-M"
                    else "sem dados"))
                continue
            last24 = enr[-_MONTHS_TABLE:]
            last24.reverse()
            rows = [[_br_month(r["ref_date"]), _pct(r.get("value")),
                     _pct(r.get("acum_12m"))] for r in last24]
            sections.append(table_section(
                f"{name} — mensal", ["Mês", "Mês (%)", "Acum. 12m (%)"],
                rows, description="Últimos 24 meses.",
            ))
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Câmbio ──────────────────────────────────────────────────────────────
    def cambio(self) -> dict[str, Any]:
        """Onde está o câmbio — USD/BRL ptax diária + média mensal."""
        fx = _sgs_series(code=USD_BRL, days=_DAYS)
        if _sgs_unavailable(fx):
            return _sgs_error_payload()

        obs = fx.get("observations", [])
        last = obs[-1] if obs else {}
        monthly = _monthly_avg(obs)
        m_last = monthly[-1] if monthly else {}

        # 12-month window stats over daily observations.
        year_obs = [o for o in obs
                    if o.get("ref_date", "") >=
                    f"{_dt.now().year - 1}-{'%02d' % _dt.now().month}-01"]
        vals_12m = [o.get("value") for o in year_obs
                    if o.get("value") is not None]

        kpis = [
            kpi("USD/BRL (ptax)", _brl4(last.get("value")),
                "Dólar venda — taxa ptax. "
                f"Ref: {_fmt_date(last.get('ref_date'))}."),
            kpi("Média do último mês", _brl4(m_last.get("value")),
                f"Média diária de {_fmt_month(m_last.get('ref_date'))}."),
            kpi("Máxima 12m", _brl4(max(vals_12m) if vals_12m else None),
                "Maior ptax dos últimos 12 meses."),
            kpi("Mínima 12m", _brl4(min(vals_12m) if vals_12m else None),
                "Menor ptax dos últimos 12 meses."),
        ]

        sections = [
            _history_chart(
                "USD/BRL ptax — diária (R$)",
                [_line_ds("USD/BRL", [o.get("value") for o in obs], _C_FX)],
                [o["ref_date"] for o in obs], y_title="R$",
                description="Taxa ptax de venda, cotação diária.",
            ),
        ]
        if monthly:
            m_last24 = monthly[-_FX_TABLE:]
            sections.append(_history_chart(
                "USD/BRL — média mensal (R$)",
                [_line_ds("Média mensal",
                          [o.get("value") for o in monthly], _C_FX)],
                [o["ref_date"] for o in monthly], y_title="R$",
                description="Média das cotações diárias de cada mês.",
            ))
            show = list(reversed(m_last24))
            rows = [[_br_month(m["ref_date"][:7]), _brl4(m.get("value"))]
                    for m in show]
            sections.append(table_section(
                "USD/BRL — média mensal", ["Mês", "Média (R$)"], rows,
                description=f"Últimos {_FX_TABLE} meses (média das ptax "
                            "diárias).",
            ))
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Atividade ───────────────────────────────────────────────────────────
    def atividade(self) -> dict[str, Any]:
        """Como está a atividade — PIB nominal trimestral + salário mínimo."""
        pib = _sgs_series(code=PIB_NOMINAL, days=_DAYS)
        sal = _sgs_series(code=SALARIO_MIN, days=_DAYS)
        if _sgs_unavailable(pib) and _sgs_unavailable(sal):
            return _sgs_error_payload()

        p_obs = pib.get("observations", []) if pib.get("status") == "ok" else []
        s_obs = sal.get("observations", []) if sal.get("status") == "ok" else []

        p_last = p_obs[-1] if p_obs else {}
        p_prev = p_obs[-2] if len(p_obs) > 1 else {}
        var = None
        if p_last.get("value") and p_prev.get("value"):
            var = (p_last["value"] / p_prev["value"] - 1.0) * 100.0
        s_last = s_obs[-1] if s_obs else {}

        kpis = [
            kpi("PIB nominal (trim.)", _tri_br(p_last.get("value")),
                "Produto Interno Bruto nominal do último trimestre. "
                f"Ref: {_fmt_quarter(p_last.get('ref_date'))}."),
            kpi("Variação vs trim. anterior", _pct(var),
                "Variação nominal em relação ao trimestre anterior "
                "(não é a variação real do PIB)."),
            kpi("Salário mínimo", _brl2(s_last.get("value")),
                f"Vigente desde {_fmt_month(s_last.get('ref_date'))}."),
        ]

        sections: list[dict[str, Any]] = []

        if p_obs:
            # PIB em R$ milhões → R$ bilhões para o eixo ler bem.
            sections.append(_history_chart(
                "PIB nominal trimestral (R$ bi)",
                [_line_ds("PIB nominal",
                          [round(o.get("value") / 1_000.0, 2)
                           if o.get("value") is not None else None
                           for o in p_obs], _C_PIB)],
                [o["ref_date"] for o in p_obs], y_title="R$ bi",
                description="Soma do valor adicionado + impostos — nominal, "
                            "não descontada a inflação.",
            ))
            last8 = list(reversed(p_obs[-8:]))   # newest first
            rows = []
            for j, o in enumerate(last8):
                # Chronological index of o is L-1-j; its previous quarter
                # is L-2-j (None when the window runs out of history).
                prev = p_obs[len(p_obs) - 2 - j] \
                    if len(p_obs) - 2 - j >= 0 else None
                rows.append([_fmt_quarter(o.get("ref_date")),
                             _tri_br(o.get("value")),
                             _pct(_q_var(o, prev))])
            sections.append(table_section(
                "PIB — últimos trimestres",
                ["Trimestre", "PIB nominal", "Var. trim. ant."], rows,
            ))
        else:
            sections.append(_err_note("PIB", pib.get("error", "sem dados")))

        if s_obs:
            sections.append(_history_chart(
                "Salário mínimo (R$)",
                [_line_ds("Salário mínimo",
                          [o.get("value") for o in s_obs], _C_SAL)],
                [o["ref_date"] for o in s_obs], y_title="R$",
            ))
            last24 = list(reversed(s_obs[-_MONTHS_TABLE:]))
            rows = [[_br_month(o["ref_date"][:7]), _brl2(o.get("value"))]
                    for o in last24]
            sections.append(table_section(
                "Salário mínimo — vigência", ["Mês", "Valor (R$)"], rows,
                description="Valor vigente em cada mês (ajustes anuais).",
            ))
        else:
            sections.append(_err_note("Salário mínimo",
                                      sal.get("error", "sem dados")))
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Retorno Real (Fisher) ───────────────────────────────────────────────
    def retorno_real(self) -> dict[str, Any]:
        """Quanto rende o dinheiro — equação de Fisher (Selic vs IPCA 12m).

        real = (1 + nominal) / (1 + inflação) − 1, com nominal = Selic
        anualizada (série 11 × 252) e inflação = IPCA acumulado 12m. A
        Selic diária é casada com o IPCA acumulado do seu mês — o gráfico
        anda dia a dia com a Selic e degrada mês a mês com o IPCA.
        """
        selic = _sgs_series(code=SELIC_DAILY, days=_DAYS)
        if _sgs_unavailable(selic):
            return _sgs_error_payload()
        ipca = _sgs_series(code=IPCA_MENSAL, days=_MONTHS)
        if _sgs_unavailable(ipca):
            return _sgs_error_payload()

        s_obs = selic.get("observations", [])
        i_obs = ipca.get("observations", [])
        i_enr = _rolling_12m(i_obs)
        i_by_month = {r["ref_date"][:7]: r.get("acum_12m") for r in i_enr}

        s_last = s_obs[-1] if s_obs else {}
        i_last = i_enr[-1] if i_enr else {}
        nominal = _annualize(s_last.get("value"))
        infl = i_last.get("acum_12m")
        real = _fisher(nominal, infl)

        kpis = [
            kpi("Selic nominal (a.a.)", _pct(nominal),
                f"Ref: {_fmt_date(s_last.get('ref_date'))}."),
            kpi("IPCA acumulado 12m", _pct(infl),
                f"Ref: {_fmt_month(i_last.get('ref_date'))}."),
            kpi("Retorno real (Fisher)", _pct(real),
                "(1 + Selic) / (1 + IPCA 12m) − 1. Positivo = o dinheiro "
                "rende acima da inflação; negativo = o poder de compra é "
                "corroído."),
        ]

        labels = [o["ref_date"] for o in s_obs]
        selic_aa = [_annualize(o.get("value")) for o in s_obs]
        ipca_joined = [i_by_month.get(d[:7]) for d in labels]
        real_series = [_fisher(n, i) for n, i in zip(selic_aa, ipca_joined)]

        sections = [
            _history_chart(
                "Taxa real — Selic vs IPCA acumulado 12m (% a.a.)",
                [
                    _line_ds("Retorno real", real_series, _C_REAL),
                    _line_ds("Selic nominal", selic_aa, _C_CDI, dash=True),
                    _line_ds("IPCA 12m", ipca_joined, _C_IPCA, dash=True),
                ],
                labels, y_title="% a.a.",
                description="Retorno real = (1 + Selic) / (1 + IPCA 12m) − 1 "
                            "(Fisher). A Selic é diária; o IPCA acumulado é "
                            "o do mês de cada ponto.",
            ),
        ]

        # Monthly table — month-end Selic (a.a.) + IPCA 12m + real.
        s_monthly = _month_end_series(s_obs)
        rows = []
        for m in reversed(s_monthly[-_MONTHS_TABLE:]):
            i12 = i_by_month.get(m["ref_date"][:7])
            n = _annualize(m.get("value"))
            rows.append([_br_month(m["ref_date"]), _pct(n), _pct(i12),
                         _pct(_fisher(n, i12))])
        sections.append(table_section(
            "Retorno real — mensal",
            ["Mês", "Selic (a.a.)", "IPCA 12m (%)", "Real (%)"], rows,
            description="Fim do mês: Selic anualizada, IPCA acumulado 12m e "
                        "o retorno real de Fisher.",
        ))
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Expectativas Focus ──────────────────────────────────────────────────
    def focus(self) -> dict[str, Any]:
        """O que o mercado espera — Focus: IPCA, Selic e Câmbio.

        Mediana (linha sólida) + faixa mínimo/máximo (tracejadas) por
        indicador. Faixa larga = incerteza alta; faixa estreita = consenso.
        """
        panels = [
            ("IPCA", "monthly", "%", _C_IPCA,
             "Expectativas mensais para o IPCA (12 meses de referência à "
             "frente)."),
            ("Selic", "annual", "% a.a.", _C_SELIC,
             "Expectativas anuais para a Selic (ano-calendário de "
             "referência)."),
            ("Câmbio", "monthly", "R$", _C_FX,
             "Expectativas mensais para a taxa USD/BRL."),
        ]

        kpis: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        any_ok = False

        for indicador, frequency, unit, color, desc in panels:
            res = _safe_focus(indicador, frequency)
            if res.get("status") != "ok":
                sections.append(_err_note(
                    f"Focus — {indicador}",
                    res.get("error", "sem dados")))
                kpis.append(kpi(f"{indicador} (mediana)", "-",
                                "Sem expectativas registradas."))
                continue
            any_ok = True
            obs = _dedupe_focus(res.get("observations", []))
            if not obs:
                sections.append(_err_note(f"Focus — {indicador}",
                                          "sem observações"))
                kpis.append(kpi(f"{indicador} (mediana)", "-", ""))
                continue

            latest = obs[0]     # sorted DESC by survey date
            kpis.append(kpi(
                f"{indicador} (mediana)",
                _fmt_focus(latest.get("mediana"), unit),
                f"Ref: {latest.get('data_referencia', '-')} · "
                f"{latest.get('numero_respondentes', '-')} respondentes · "
                f"pesquisa de {_fmt_date(latest.get('data'))}.",
            ))

            asc = sorted([o for o in obs if o.get("data")],
                         key=lambda o: o["data"])
            labels = [o["data"] for o in asc]
            sections.append(_history_chart(
                f"{indicador} — expectativas ({unit})",
                [
                    _line_ds("Mediana",
                             [o.get("mediana") for o in asc], color),
                    _line_ds("Máximo", [o.get("maximo") for o in asc],
                             _C_MAX, dash=True),
                    _line_ds("Mínimo", [o.get("minimo") for o in asc],
                             _C_MIN, dash=True),
                ],
                labels, y_title=unit,
                description=desc + " Mediana sólida; máximo/mínimo "
                            "tracejados — a dispersão das previsões.",
            ))

            show = obs[:15]
            rows = [[_fmt_date(o.get("data")), o.get("data_referencia", "-"),
                     _fmt_focus(o.get("media"), unit),
                     _fmt_focus(o.get("mediana"), unit),
                     _fmt_focus(o.get("minimo"), unit),
                     _fmt_focus(o.get("maximo"), unit),
                     fmt_int(o.get("numero_respondentes"))]
                    for o in show]
            sections.append(table_section(
                f"{indicador} — últimas expectativas",
                ["Data", "Data Ref.", "Média", "Mediana", "Mínimo",
                 "Máximo", "Resp."],
                rows,
                description="Últimas pesquisas registradas (top 15, "
                            "deduplicado por data + referência).",
            ))

        if not any_ok:
            return _focus_error_payload()
        return {"status": "ok", "kpis": kpis, "sections": sections}

    # ── Curva de Juros ──────────────────────────────────────────────────────
    def curva(self) -> dict[str, Any]:
        """Qual caminho de taxas está precificado — Selic Focus por ano.

        Para cada ano de referência, a última mediana Focus + faixa
        mínimo/máximo. KPIs: Selic atual (Meta Copom), esperada no próximo
        ano e de longo prazo (+5 anos, ou o mais distante disponível).
        """
        # 1. Selic atual (SGS 432) — degrada com o Focus, não com o SGS.
        meta = _last(META_COPOM)
        current = None
        if meta.get("status") == "ok":
            current = meta.get("value")

        res = _safe_focus("Selic", "annual")
        if res.get("status") != "ok":
            if current is None:
                return _focus_error_payload()
            # Partial: SGS ok + Focus missing → KPI atual + nota.
            return {
                "status": "ok",
                "kpis": [kpi("Selic atual (Meta Copom)", _pct(current),
                             f"Ref: {_fmt_date(meta.get('ref_date'))}.")],
                "sections": [_err_note(
                    "Curva de Juros",
                    "expectativas Focus indisponíveis — sincronize a fonte "
                    "focus na página Sincronização.")],
            }

        obs = _dedupe_focus(res.get("observations", []))
        # Primeira ocorrência de cada ano = expectativa mais recente
        # (observations vêm DESC por data de pesquisa).
        latest_by_year: dict[str, dict[str, Any]] = {}
        for o in obs:
            yr = o.get("data_referencia") or ""
            if yr and yr not in latest_by_year:
                latest_by_year[yr] = o
        years = sorted([y for y in latest_by_year if y.isdigit()],
                       key=int)
        if not years:
            return _focus_error_payload()

        points = [latest_by_year[y] for y in years]
        kpis = [
            kpi("Selic atual (Meta Copom)", _pct(current),
                f"Ref: {_fmt_date(meta.get('ref_date'))}."),
        ]
        next_year = str(_dt.now().year + 1)
        p_next = next((p for p in points if p.get("data_referencia") ==
                       next_year), None)
        kpis.append(kpi(
            f"Selic esperada {next_year}",
            _pct(p_next.get("mediana")) if p_next else "-",
            f"Mediana Focus. Ref: {next_year}."
            + (f" Pesquisa de {_fmt_date(p_next.get('data'))}."
               if p_next else "")))
        long_year = str(_dt.now().year + 5)
        p_long = next((p for p in points if p.get("data_referencia") ==
                       long_year), None) or points[-1]
        kpis.append(kpi(
            f"Selic longo prazo ({p_long.get('data_referencia')})",
            _pct(p_long.get("mediana")),
            f"Mediana Focus. Ref: {p_long.get('data_referencia')}. "
            f"Pesquisa de {_fmt_date(p_long.get('data'))}.",
        ))

        # Chart — years on x (NOT a date axis; no range selector: this is a
        # forward-looking curve, not a historical range).
        cd = {
            "type": "line",
            "data": {
                "labels": [p.get("data_referencia") for p in points],
                "datasets": [
                    _line_ds("Mediana", [p.get("mediana") for p in points],
                             _C_SELIC, point_radius=3),
                    _line_ds("Máximo", [p.get("maximo") for p in points],
                             _C_MAX, dash=True, point_radius=2),
                    _line_ds("Mínimo", [p.get("minimo") for p in points],
                             _C_MIN, dash=True, point_radius=2),
                ],
            },
            "options": {"scales": {
                "x": {"title": {"display": True, "text": "Ano de referência"}},
                "y": {"title": {"display": True, "text": "% a.a."}},
            }},
        }
        sections = [
            chart_section(
                "Curva de juros esperada — Selic (Focus)", cd,
                description="Mediana das expectativas da Pesquisa Focus "
                            "(BCB) para a Selic em cada ano de referência + "
                            "faixa mínimo/máximo. Faixa larga = alta "
                            "incerteza; faixa estreita = consenso.",
            ),
            table_section(
                "Expectativas Selic por ano",
                ["Ano", "Mediana", "Mínimo", "Máximo", "Resp.",
                 "Data Focus"],
                [[p.get("data_referencia"),
                  _pct(p.get("mediana")), _pct(p.get("minimo")),
                  _pct(p.get("maximo")),
                  fmt_int(p.get("numero_respondentes")),
                  _fmt_date(p.get("data"))] for p in points],
                description="Última expectativa registrada para cada ano.",
            ),
        ]
        return {"status": "ok", "kpis": kpis, "sections": sections}


# ── module-level helpers ─────────────────────────────────────────────────────
def _fmt_month(ref: Any) -> Any:
    """'2026-10-01' / '2026-10' → 'out/2026'."""
    if isinstance(ref, str) and len(ref) >= 7:
        return _br_month(ref[:7])
    return ref


def _fmt_quarter(ref: Any) -> Any:
    """'2026-07-01' → 'T3 2026' (PIB trimestral reads as quarters)."""
    if isinstance(ref, str) and len(ref) >= 7:
        month = int(ref[5:7])
        q = (month - 1) // 3 + 1
        return f"T{q} {ref[:4]}"
    return ref


def _q_var(cur: dict[str, Any], prev: dict[str, Any] | None) -> Any:
    """Variação % do PIB vs trimestre anterior (nominal)."""
    if not prev:
        return None
    c, p = cur.get("value"), prev.get("value")
    if c is None or p in (None, 0):
        return None
    return (c / p - 1.0) * 100.0


def _fisher(nominal: float | None, inflacao: float | None) -> float | None:
    """Fisher real rate: (1 + n)/(1 + i) − 1 (values in %)."""
    if nominal is None or inflacao is None:
        return None
    n, i = nominal / 100.0, inflacao / 100.0
    if 1.0 + i == 0.0:
        return None
    return ((1.0 + n) / (1.0 + i) - 1.0) * 100.0


def _fmt_focus(v: Any, unit: str) -> str:
    """Focus values: 2 decimais para %, 4 para R$ (câmbio)."""
    if v is None:
        return "-"
    return _brl4(v) if unit == "R$" else _pct(v)


def _safe_focus(indicador: str, frequency: str) -> dict[str, Any]:
    """focus query that never raises (not_synced → clean degradation)."""
    try:
        return _focus_expectations(indicador=indicador,
                                   frequency=frequency, limit=2000)
    except Exception as e:  # noqa: BLE001 — degraded path, logged
        print(f"[webui-macro] focus({indicador}/{frequency}) failed: {e}",
              file=sys.stderr)
        return {"status": "error", "error": str(e)}
