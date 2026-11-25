"""webui/services/shareholders.py — Acionistas tab data service.

[v1.9] The CVM shareholders view for the company page — a reorganized take
on the static ``PETR4_shareholders_dashboard.html`` reference (built by
skills/cvm/shareholders/modes/dashboard.py). Same data layer (FRE
posicao_acionaria + distribuicao_capital + capital_social + DFP BPP 2.03.*),
but organized around the questions an investor asks about ownership, not
around the static report's four flat tabs (its Overview duplicated the
identity card + price chart the WebUI already renders above the tabs):

  overview   → "who controls, who floats?"  (KPIs + the CURRENT snapshot —
               controle × free float + concentração top-N; [v1.26.1 fix1]
               the evolução charts moved out — they live in free_float)
  holders    → "who are the shareholders?"  (full posição acionária table
               with % ON / % PN / % Total — the static showed only the top-5
               % Total, which hides that FRE percentages are per class)
  free_float → "how is the capital distributed?"  (evolution + PF/PJ/Inst
               counts — the static shipped a single-row table)
  equity     → "what is the equity made of?"  (BPP 2.03.* + FRE capital
               social; the static showed one snapshot, here it evolves)

Every method returns the v1.7 FLAT contract payload
(``{"ticker", "status": "ok", "kpis"?, "sections"}``). All subtabs render
through the generic renderer (loadShSubtab → valKpisHtml + valSectionsHtml
+ mountValCharts in app.js) — no custom client code beyond the loader.

Data conventions (same as v1.8 fix1):
  - Every date the user READS (table cells, prose refs) is dd/mm/yyyy via
    ``_fmt_date``; non-ISO strings pass through so degraded "-" survives.
  - Chart labels ship ISO on purpose — renderValChart detects all-ISO x
    labels and formats ticks + tooltip titles client-side.

FRE percentages (pct_on/pct_pn/pct_total) are plain percent numbers stored
by CVM (45.23 = 45,23%) — formatted with fmt_pct(already_percent=True).
Equity values (BPP 2.03.*) are compact BRL (fmt_brl suffix=True →
"R$ 415,79 bi") in tables/KPIs and R$ billions in charts.

Graceful degradation mirrors the skill's contract: a missing fre.db drops
the FRE sections (KPIs become "-"); a missing dfp.db drops only the equity
KPIs/table; total failure (nothing resolves) returns the canonical
``_error`` payload telling the user which source to sync.
"""
from __future__ import annotations

import datetime as _dt
import re as _re
import sys
from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    kpi,
    table_section,
    two_column_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.cvm.fre.query_engine import (
    capital as _fre_capital,
    free_float as _fre_free_float,
    shareholders as _fre_shareholders,
)
from skills.cvm.shareholders.modes.equity_structure import (
    equity_structure as _dfp_equity_structure,
)
from tools.report_ops.formats import fmt_brl, fmt_int, fmt_pct

# Palette (same accents as the static dashboard / the rest of the UI).
_COLOR_FF = "#0d9488"       # teal   — % Total circulação (free float)
_COLOR_ON = "#f59e0b"       # amber  — % ON circulação
_COLOR_PN = "#8b5cf6"       # violet — % PN circulação
_COLOR_PF = "#14b8a6"       # teal   — acionistas PF (stacked)
_COLOR_PJ = "#f59e0b"       # amber  — acionistas PJ (stacked)
_COLOR_INST = "#64748b"     # slate  — acionistas institucionais (stacked)
_COLOR_PL = "#0d9488"       # teal   — PL Total (line)
_COLOR_CAP = "#f59e0b"      # amber  — Capital Social (line)
_DOUGHNUT_COLORS = ["#0d9488", "#f59e0b", "#3b82f6", "#a855f7", "#ef4444",
                    "#94a3b8"]

# BPP 2.03.* code → (short label, tooltip label) — same codes the skill's
# equity_structure mode + the static dashboard use.
_EQUITY_CODES = [
    ("2.03",    "PL Total",            "Patrimônio Líquido Total (BPP 2.03)"),
    ("2.03.01", "Capital Social",      "Capital Social Realizado (BPP 2.03.01)"),
    ("2.03.02", "Reservas de Capital", "Reservas de Capital (BPP 2.03.02)"),
    ("2.03.04", "Reservas de Lucros",  "Reservas de Lucros (BPP 2.03.04)"),
    ("2.03.05", "Lucros Acumulados",   "Lucros/Prejuízos Acumulados (BPP 2.03.05)"),
    ("2.03.09", "Minoritários",        "Participação de Acionistas Não "
                                       "Controladores (BPP 2.03.09)"),
]

# Shareholder table cap — FRE filings carry dozens of named holders for
# complex structures; the WebUI caps the render and says the real count.
_HOLDERS_CAP = 60


# [v1.9] ISO date detector — same convention as options.py (v1.8 fix1).
_ISO_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fmt_date(s: Any) -> Any:
    """ISO "2026-12-31" → "31/12/2026" (padrão brasileiro).

    Non-ISO values (None, "-", "", already formatted) pass through
    untouched so degraded paths keep their placeholders. Chart labels are
    the deliberate exception — they ship ISO and the client formats the
    axis ticks + tooltip titles (v1.8 fix1 convention).
    """
    if isinstance(s, str) and _ISO_DATE_RE.match(s):
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def _log_err(where: str, e: BaseException) -> None:
    print(f"[webui-shareholders] {where}: {type(e).__name__}: {e}",
          file=sys.stderr)


def _safe(fn, **kwargs) -> dict:
    """Call a query-engine function defensively (missing DB → error dict,
    so one broken source degrades sections, never the whole tab)."""
    try:
        return fn(**kwargs)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash the tab
        _log_err(kwargs.get("company", ""), e)
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _pct(v: Any) -> str:
    """FRE plain percent (45.23 → "45,23%") — CVM stores percent numbers."""
    return fmt_pct(v, already_percent=True)


def _trunc(s: str, n: int = 26) -> str:
    """Truncate long shareholder names for chart labels / KPI values."""
    s = (s or "").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


def _fmt_cnpj_cpf(raw: Any) -> str:
    """Mask a raw digits string as CNPJ (00.000.000/0000-00) or CPF
    (000.000.000-00). Anything else passes through as-is."""
    if not isinstance(raw, str):
        return raw if raw else "—"
    d = _re.sub(r"\D", "", raw)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return raw


class ShareholdersService:
    """Acionistas data service — one method per lazy subtab.

    All queries are read-only SQLite over the synced FRE/DFP DBs; no
    caching (single-digit ms queries, lazy per ticker — same policy as
    OptionsService).
    """

    # ── shared helpers ────────────────────────────────────────────────────

    def _ff_charts(self, periods: list[dict]) -> list[dict[str, Any]]:
        """The two evolution charts (free float % + acionistas counts),
        chronological order. Only drawn with 2+ periods — a single filing
        has no evolution to show (the static dashboard shipped a one-row
        table; here the table carries that case)."""
        out: list[dict[str, Any]] = []
        chron = list(reversed(periods))  # query returns DESC
        labels = [p.get("data_referencia") or "" for p in chron]
        if len(chron) < 2 or not all(labels):
            return out

        has_pct = any(p.get("pct_total_circulacao") is not None
                      or p.get("pct_on_circulacao") is not None
                      or p.get("pct_pn_circulacao") is not None
                      for p in chron)
        if has_pct:
            out.append(chart_section(
                "Evolução do Free Float (%)",
                {
                    "type": "line",
                    "data": {
                        "labels": labels,
                        "datasets": [
                            {"label": "% Total Circulação",
                             "data": [p.get("pct_total_circulacao")
                                      for p in chron],
                             "borderColor": _COLOR_FF,
                             "backgroundColor": _COLOR_FF},
                            {"label": "% ON Circulação",
                             "data": [p.get("pct_on_circulacao")
                                      for p in chron],
                             "borderColor": _COLOR_ON,
                             "backgroundColor": _COLOR_ON},
                            {"label": "% PN Circulação",
                             "data": [p.get("pct_pn_circulacao")
                                      for p in chron],
                             "borderColor": _COLOR_PN,
                             "backgroundColor": _COLOR_PN},
                        ],
                    },
                    "options": {"scales": {
                        "y": {"beginAtZero": True, "title": {
                            "display": True, "text": "% em circulação"}},
                    }},
                },
                description=(
                    "Percentual de ações em circulação (free float) por "
                    "data de referência do FRE. ON/PN/Total conforme "
                    "declarado em cada formulário anual."
                ),
            ))

        has_counts = any(p.get("qtd_acionistas_pf") is not None
                         or p.get("qtd_acionistas_pj") is not None
                         or p.get("qtd_acionistas_inst") is not None
                         for p in chron)
        if has_counts:
            out.append(chart_section(
                "Evolução de Acionistas (PF/PJ/Inst.)",
                {
                    "type": "bar",
                    "data": {
                        "labels": labels,
                        "datasets": [
                            {"label": "PF", "data": [p.get("qtd_acionistas_pf")
                                                     for p in chron],
                             "backgroundColor": _COLOR_PF},
                            {"label": "PJ", "data": [p.get("qtd_acionistas_pj")
                                                     for p in chron],
                             "backgroundColor": _COLOR_PJ},
                            {"label": "Institucionais", "data": [
                                p.get("qtd_acionistas_inst") for p in chron],
                             "backgroundColor": _COLOR_INST},
                        ],
                    },
                    "options": {"scales": {
                        "x": {"stacked": True},
                        "y": {"stacked": True, "beginAtZero": True,
                              "title": {"display": True,
                                        "text": "Acionistas"}},
                    }},
                },
                description=(
                    "Quantidade de acionistas por data de referência: "
                    "pessoas físicas (PF), jurídicas (PJ) e investidores "
                    "institucionais, empilhados."
                ),
            ))
        return out

    def _ff_kpis(self, latest: dict) -> list[dict[str, Any]]:
        """The free float KPI trio + total acionistas (latest period)."""
        pf = latest.get("qtd_acionistas_pf")
        pj = latest.get("qtd_acionistas_pj")
        inst = latest.get("qtd_acionistas_inst")
        total = None
        if any(v is not None for v in (pf, pj, inst)):
            total = (pf or 0) + (pj or 0) + (inst or 0)
        ref = _fmt_date(latest.get("data_referencia"))
        return [
            kpi("% Free Float", _pct(latest.get("pct_total_circulacao")),
                "% das ações em circulação (ON+PN) conforme o FRE"
                + (f" (ref: {ref})." if ref and ref != "-" else ".")),
            kpi("Total Acionistas", fmt_int(total),
                "Acionistas PF + PJ + institucionais na última declaração"
                + (f" (ref: {ref})." if ref and ref != "-" else ".")),
            kpi("Acionistas PF", fmt_int(pf),
                "Pessoas físicas com posição declarada."),
            kpi("Acionistas PJ", fmt_int(pj),
                "Pessoas jurídicas com posição declarada."),
            kpi("Acionistas Inst.", fmt_int(inst),
                "Investidores institucionais com posição declarada."),
        ]

    def _ff_table(self, periods: list[dict]) -> dict[str, Any]:
        """The full free float table (all periods, newest first)."""
        sec = table_section(
            "Free Float / Distribuição de Acionistas",
            ["Data Referência", "% ON Circ.", "% PN Circ.", "% Total Circ.",
             "Acionistas PF", "Acionistas PJ", "Acionistas Inst.",
             "Últ. Assembleia"],
            [[_fmt_date(p.get("data_referencia")),
              _pct(p.get("pct_on_circulacao")),
              _pct(p.get("pct_pn_circulacao")),
              _pct(p.get("pct_total_circulacao")),
              fmt_int(p.get("qtd_acionistas_pf")),
              fmt_int(p.get("qtd_acionistas_pj")),
              fmt_int(p.get("qtd_acionistas_inst")),
              _fmt_date(p.get("data_ultima_assembleia"))]
             for p in periods],
            description=(
                "Todas as datas de referência do FRE (mais recente "
                "primeiro). % Circulação = fração das ações da classe em "
                "mercado (exclui o bloco de controle)."
            ),
            note=(f"{len(periods)} período(s) — FRE, tabela "
                  "distribuicao_capital."),
        )
        sec["sortable"] = True
        return sec

    @staticmethod
    def _sh_rows(shareholders: list[dict]) -> list[list[Any]]:
        """FRE posição acionária rows — name keeps a tooltip with the full
        name (names run long); CPF/CNPJ gets the punctuation mask."""
        return [
            [{"text": _trunc(s.get("acionista", ""), 40),
              "tooltip": s.get("acionista", "")},
             _fmt_cnpj_cpf(s.get("cpf_cnpj")) or "—",
             s.get("tipo_pessoa") or "—",
             _pct(s.get("pct_on")),
             _pct(s.get("pct_pn")),
             _pct(s.get("pct_total")),
             fmt_int(s.get("qtd_total")),
             "Sim" if s.get("controlador") else "Não"]
            for s in shareholders
        ]

    def _sh_table(self, shareholders: list[dict], ref: Any) -> dict[str, Any]:
        shown = shareholders[:_HOLDERS_CAP]
        sec = table_section(
            "Posição Acionária (FRE)",
            ["Acionista", "CPF/CNPJ", "Tipo", "% ON", "% PN", "% Total",
             "Qtde Total", "Controlador"],
            self._sh_rows(shown),
            description=(
                "Posição acionária declarada no Formulário de Referência. "
                "% ON / % PN = fração de CADA CLASSE detida pelo acionista; "
                "% Total = fração do total de ações (ON+PN). Um mesmo nome "
                "pode aparecer em mais de uma linha (declarações distintas "
                "por CPF/CNPJ)."
            ),
            note=(f"Data de referência: {_fmt_date(ref)}. "
                  + (f"Exibindo {len(shown)} de {len(shareholders)} "
                     "acionistas." if len(shown) < len(shareholders)
                     else f"{len(shown)} acionista(s).")),
        )
        sec["sortable"] = True
        return sec

    def _top5_doughnut(self, shareholders: list[dict]) -> dict[str, Any] | None:
        """Top-5 by % Total as a doughnut + a remainder slice when the
        declared percentages leave room (clamped at 0 — amended filings can
        double-count classes, the static dashboard's doughnut summed past
        100% with no explanation). Duplicate names get a CNPJ tail so the
        legend disambiguates them."""
        top = shareholders[:5]
        if not top:
            return None
        names: list[str] = []
        seen: dict[str, int] = {}
        for s in top:
            nm = _trunc(s.get("acionista", "") or "—", 24)
            if nm in seen:
                d = _re.sub(r"\D", "", s.get("cpf_cnpj") or "")
                tail = d[-4:] if len(d) >= 4 else (s.get("cpf_cnpj") or "")
                nm = f"{nm} (…{tail})" if tail else f"{nm} (2)"
            seen[nm] = 1
            names.append(nm)
        values = [round(float(s.get("pct_total") or 0), 2) for s in top]
        declared = sum(values)
        remainder = round(100.0 - declared, 2)
        if remainder > 0.005:
            names.append("Outros / free float")
            values.append(remainder)
        colors = _DOUGHNUT_COLORS[: len(values)]
        return chart_section(
            "Distribuição — Principais Acionistas",
            {
                "type": "doughnut",
                "data": {
                    "labels": names,
                    "datasets": [{
                        "data": values,
                        "backgroundColor": colors,
                        "borderColor": "#ffffff",
                        "borderWidth": 2,
                    }],
                },
                "options": {"cutout": "60%"},
            },
            description=(
                "Top 5 acionistas por % Total do capital (ON+PN). "
                + ("A fatia \"Outros / free float\" é o restante até 100%."
                   if remainder > 0.005 else
                   "Percentuais declarados somam 100% ou mais (declarações "
                   "por classe podem sobrepor) — sem fatia de remanescente.")
            ),
        )

    # ── 1/4: Visão Geral ──────────────────────────────────────────────────

    def overview(self, ticker: str) -> dict[str, Any]:
        """The ownership state on one screen.

        6 KPI cards (% Free Float / Total Acionistas / PL Total /
        Capital Social / Ações Totais / Maior Acionista) + the CURRENT
        ownership snapshot + a Mercado|Patrimônio two-column.

        [v1.26.1 fix1] This view used to repeat the other subtabs — the
        two evolution charts lived (still live) in Free Float and the
        top-5 preview table in Posição Acionária. The overview now shows
        what only it can, the CURRENT structure: a controle × free float
        doughnut + a top-N declared-holder concentration bar (measured in
        quantities ÷ total emitido — robust to the per-class % Total
        declarations that can sum past 100%).
        """
        tk = (ticker or "").upper()
        ff = _safe(_fre_free_float, company=tk)
        sh = _safe(_fre_shareholders, company=tk, limit=_HOLDERS_CAP)
        eq = _safe(_dfp_equity_structure, company=tk, periods=1)
        cap = _safe(_fre_capital, company=tk)

        ff_ok = ff.get("status") == "ok" and ff.get("periods")
        sh_ok = sh.get("status") == "ok" and sh.get("shareholders")
        eq_ok = eq.get("status") == "ok" and eq.get("periods")
        cap_ok = cap.get("status") == "ok" and cap.get("periods")

        if not (ff_ok or sh_ok or eq_ok or cap_ok):
            return error_payload(
                tk, "Sem dados de acionistas — sincronize a fonte fre "
                    "(FRE — Formulário de Referência) na página "
                    "Sincronização (e dfp para a estrutura patrimonial).")

        latest_ff = (ff["periods"][0] if ff_ok else {})
        pf, pj, inst = (latest_ff.get("qtd_acionistas_pf"),
                        latest_ff.get("qtd_acionistas_pj"),
                        latest_ff.get("qtd_acionistas_inst"))
        total_owners = None
        if any(v is not None for v in (pf, pj, inst)):
            total_owners = (pf or 0) + (pj or 0) + (inst or 0)
        ff_ref = _fmt_date(latest_ff.get("data_referencia"))

        accounts = ((eq["periods"][0].get("accounts") or {})
                    if eq_ok else {})
        eq_ref = _fmt_date(eq["periods"][0].get("data_fim_exerc")) if eq_ok else "-"
        pl_total = accounts.get("2.03", {}).get("valor_brl")

        latest_cap = (cap["periods"][0] if cap_ok else {})
        valor_cap = latest_cap.get("valor_capital")
        qtd_total_sh = latest_cap.get("qtd_acoes_total")
        cap_ref = _fmt_date(latest_cap.get("data_referencia"))

        # Maior acionista por quantidade declarada (qtd_total) — % Total
        # can double-count classes (amended filings); quantity is the
        # economic size. The "Outros" aggregate row (the free float the
        # FRE itself declares) is excluded — the % Free Float KPI already
        # tells that story. Tooltip carries the full detail.
        biggest = "-"
        biggest_tip = "Sem posição acionária declarada (FRE)."
        if sh_ok:
            by_qty = sorted(
                (s for s in sh["shareholders"]
                 if (s.get("acionista") or "").strip().lower() != "outros"),
                key=lambda s: (s.get("qtd_total") or 0), reverse=True)
            if by_qty and (by_qty[0].get("qtd_total") or 0) > 0:
                b = by_qty[0]
                biggest = _trunc(b.get("acionista", "") or "—", 26)
                biggest_tip = (
                    f"{b.get('acionista', '')} — {fmt_int(b.get('qtd_total'))} "
                    f"ações · {_pct(b.get('pct_total'))} do total (ON+PN). "
                    "Maior posição por quantidade declarada (qtd_total), "
                    "excluindo a linha agregada \"Outros\" (free float).")

        kpis = [
            kpi("% Free Float", _pct(latest_ff.get("pct_total_circulacao")),
                "% das ações em circulação (ON+PN) conforme o FRE"
                + (f" (ref: {ff_ref})." if ff_ref not in ("-", None, "")
                   else ".")),
            kpi("Total Acionistas", fmt_int(total_owners),
                "Acionistas PF + PJ + institucionais na última declaração"
                + (f" (ref: {ff_ref})." if ff_ref not in ("-", None, "")
                   else ".")),
            kpi("PL Total", fmt_brl(pl_total),
                "Patrimônio Líquido total (BPP 2.03, DFP)"
                + (f" (fim de exercício: {eq_ref})."
                   if eq_ref != "-" else ".")),
            kpi("Capital Social", fmt_brl(valor_cap),
                "Valor do capital social realizado (FRE, capital_social)"
                + (f" (ref: {cap_ref})." if cap_ref not in ("-", None, "")
                   else ".")),
            kpi("Ações Totais", fmt_int(qtd_total_sh),
                "Total de ações emitidas (ON+PN) conforme o FRE"
                + (f" (ref: {cap_ref})." if cap_ref not in ("-", None, "")
                   else ".")),
            kpi("Maior Acionista", biggest, biggest_tip),
        ]

        sections: list[dict[str, Any]] = []

        # [v1.26.1 fix1] The CURRENT ownership snapshot — the two
        # evolution charts ("Evolução do Free Float (%)" / "Evolução de
        # Acionistas (PF/PJ/Inst.)") and the top-5 preview table used to
        # render here too, duplicating the Free Float and Posição
        # Acionária subtabs one click away. An overview answers "who
        # controls, who floats?" TODAY:
        #   1. controle × free float doughnut (the declared % circulação
        #      vs the rest — control block + treasury + undeclared);
        #   2. top-N declared-holder concentration, in quantities ÷ total
        #      emitido (NOT % Total — amended per-class declarations can
        #      double-count; quantities can't), with the declared free
        #      float as the reference bar. "Outros" (the FRE's own
        #      free-float aggregate row) is excluded from the tops.
        ff_pct = latest_ff.get("pct_total_circulacao")

        if ff_ok and ff_pct is not None:
            ff_v = max(0.0, min(100.0, float(ff_pct)))
            sections.append(chart_section(
                "Estrutura de Propriedade — Atual",
                {
                    "type": "doughnut",
                    "data": {
                        "labels": ["Free Float", "Controle / Demais"],
                        "datasets": [{
                            "data": [round(ff_v, 2),
                                      round(100.0 - ff_v, 2)],
                            "backgroundColor": [_COLOR_FF, "#64748b"],
                            "borderColor": "#ffffff",
                            "borderWidth": 2,
                        }],
                    },
                    "options": {"cutout": "60%"},
                },
                description=(
                    "Retrato ATUAL da propriedade: free float declarado "
                    "no FRE"
                    + (f" (ref: {ff_ref})."
                       if ff_ref not in ("-", None, "") else ".")
                    + " O restante agrupa bloco de controle, tesouraria e "
                    "demais posições não declaradas. As evoluções "
                    "históricas ficam na subaba Free Float."
                ),
            ))

        if sh_ok and cap_ok and qtd_total_sh:
            declared = sorted(
                (s for s in sh["shareholders"]
                 if (s.get("acionista") or "").strip().lower() != "outros"
                 and (s.get("qtd_total") or 0) > 0),
                key=lambda s: s.get("qtd_total") or 0, reverse=True)
            if declared:
                total_sh = float(qtd_total_sh)
                conc_labels: list[str] = []
                conc_values: list[float] = []
                for n in (1, 5, 10):
                    if len(declared) >= n:
                        qsum = sum((s.get("qtd_total") or 0)
                                   for s in declared[:n])
                        conc_labels.append(f"Top {n}")
                        conc_values.append(
                            round(qsum / total_sh * 100.0, 2))
                if ff_pct is not None:
                    conc_labels.append("Free Float")
                    conc_values.append(
                        round(max(0.0, float(ff_pct)), 2))
                if conc_labels:
                    sections.append(chart_section(
                        "Concentração — Maiores Acionistas",
                        {
                            "type": "bar",
                            "data": {
                                "labels": conc_labels,
                                "datasets": [{
                                    "label": "% do total de ações (ON+PN)",
                                    "data": conc_values,
                                    "backgroundColor": [
                                        _COLOR_FF if lbl == "Free Float"
                                        else "#f59e0b"
                                        for lbl in conc_labels],
                                    "borderWidth": 0,
                                }],
                            },
                            "options": {"scales": {
                                "y": {"beginAtZero": True, "title": {
                                    "display": True,
                                    "text": "% do total (ON+PN)"}},
                                "x": {"ticks": {"maxTicksLimit": 6}},
                            }},
                        },
                        description=(
                            "Fatia do capital detida pelos N maiores "
                            "acionistas DECLARADOS no FRE, medida por "
                            "quantidade (qtd_total ÷ total emitido) — "
                            "robusta às declarações por classe que fazem "
                            "% Total somar mais de 100%. A linha agregada "
                            "\"Outros\" está excluída; a barra Free Float "
                            "é o percentual declarado em circulação, para "
                            "referência. Lista completa na subaba Posição "
                            "Acionária."
                        ),
                    ))

        # Mercado | Patrimônio blocks.
        if ff_ok or cap_ok or eq_ok:
            left_rows = [
                kpi("% Free Float", _pct(latest_ff.get("pct_total_circulacao")),
                    "Fração das ações em circulação (ON+PN)."),
                kpi("% ON Circulação", _pct(latest_ff.get("pct_on_circulacao")),
                    "Fração das ações ordinárias em mercado."),
                kpi("% PN Circulação", _pct(latest_ff.get("pct_pn_circulacao")),
                    "Fração das ações preferenciais em mercado."),
                kpi("Acionistas PF", fmt_int(pf),
                    "Pessoas físicas com posição declarada."),
                kpi("Acionistas PJ", fmt_int(pj),
                    "Pessoas jurídicas com posição declarada."),
                kpi("Acionistas Inst.", fmt_int(inst),
                    "Investidores institucionais com posição declarada."),
            ] if ff_ok else []
            right_rows = [
                kpi("PL Total", fmt_brl(pl_total),
                    "BPP 2.03 — Patrimônio Líquido (DFP)."),
                kpi("Capital Social", fmt_brl(valor_cap),
                    "Capital social realizado (FRE)."),
                kpi("Ações ON", fmt_int(latest_cap.get("qtd_acoes_on")),
                    "Ações ordinárias emitidas (FRE)."),
                kpi("Ações PN", fmt_int(latest_cap.get("qtd_acoes_pn")),
                    "Ações preferenciais emitidas (FRE)."),
                kpi("Ações Totais", fmt_int(qtd_total_sh),
                    "Ações emitidas ON+PN (FRE)."),
                kpi("Data de Referência", ff_ref if ff_ok else cap_ref,
                    "Data da última declaração do FRE."),
            ] if (cap_ok or ff_ok) else []
            if left_rows and right_rows:
                sections.append(two_column_section(
                    "Mercado (free float)", left_rows,
                    "Patrimônio & Capital", right_rows))
            elif right_rows:
                sections.append(two_column_section(
                    "Patrimônio & Capital", right_rows, "", []))
            elif left_rows:
                sections.append(two_column_section(
                    "Mercado (free float)", left_rows, "", []))

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 2/4: Posição Acionária ────────────────────────────────────────────

    def holders(self, ticker: str) -> dict[str, Any]:
        """The full named-shareholder table + the top-5 doughnut.

        The static dashboard's table showed only % Total for the top 5 —
        which reads wrong when FRE declares per-class percentages (rows at
        "100%"). Here the three columns (% ON / % PN / % Total) sit side
        by side, quantities and controlling status included, sortable.
        """
        tk = (ticker or "").upper()
        res = _safe(_fre_shareholders, company=tk, limit=500)
        if res.get("status") != "ok" or not res.get("shareholders"):
            return error_payload(
                tk, "Sem posição acionária — sincronize a fonte fre "
                    "(FRE — Formulário de Referência) na página "
                    "Sincronização.")
        sh = res["shareholders"]
        ref = _fmt_date(res.get("data_referencia"))
        controllers = sum(1 for s in sh if s.get("controlador"))
        top_pct = sh[0].get("pct_total") if sh else None

        kpis = [
            kpi("Acionistas Declarados", fmt_int(len(sh)),
                "Linhas de posição acionária no último formulário (um nome "
                "pode ter mais de uma linha por CPF/CNPJ distinto)."),
            kpi("Controladores", fmt_int(controllers),
                "Acionistas marcados como controladores no FRE."),
            kpi("% do Maior (declarado)", _pct(top_pct),
                "Maior % Total declarado — atenção: declarações por classe "
                "podem somar mais de 100% (ver colunas % ON / % PN)."),
            kpi("Data de Referência", ref,
                "Data de referência do Formulário de Referência."),
        ]

        sections = [self._sh_table(sh, res.get("data_referencia"))]
        doughnut = self._top5_doughnut(sh)
        if doughnut:
            sections.append(doughnut)

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 3/4: Free Float ───────────────────────────────────────────────────

    def free_float(self, ticker: str) -> dict[str, Any]:
        """Free float detail — evolution charts + the all-periods table
        (the static shipped a single-row snapshot; the FRE carries one
        row per annual filing)."""
        tk = (ticker or "").upper()
        res = _safe(_fre_free_float, company=tk)
        if res.get("status") != "ok" or not res.get("periods"):
            return error_payload(
                tk, "Sem dados de free float — sincronize a fonte fre "
                    "(FRE — Formulário de Referência) na página "
                    "Sincronização.")
        periods = res["periods"]
        latest = periods[0]

        # KPIs: the trio from the static + the ON/PN split.
        kpis = self._ff_kpis(latest)
        kpis.insert(2, kpi(
            "% ON Circ.", _pct(latest.get("pct_on_circulacao")),
            "Fração das ações ordinárias em mercado (exclui controle)."))
        kpis.insert(3, kpi(
            "% PN Circ.", _pct(latest.get("pct_pn_circulacao")),
            "Fração das ações preferenciais em mercado (exclui controle)."))

        sections = self._ff_charts(periods)
        sections.append(self._ff_table(periods))

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 4/4: Estrutura Patrimonial ────────────────────────────────────────

    def equity(self, ticker: str) -> dict[str, Any]:
        """Equity composition — BPP 2.03.* components over the years +
        the FRE capital social (share counts / valor / aprovação).

        Charts carry values in R$ billions (raw BRL would put 4,2e+11 on
        the y-axis); tables/KPIs use compact BRL ("R$ 415,79 bi").
        """
        tk = (ticker or "").upper()
        eq = _safe(_dfp_equity_structure, company=tk, periods=10)
        cap = _safe(_fre_capital, company=tk)
        eq_ok = eq.get("status") == "ok" and eq.get("periods")
        cap_ok = cap.get("status") == "ok" and cap.get("periods")

        if not (eq_ok or cap_ok):
            return error_payload(
                tk, "Sem estrutura patrimonial — sincronize as fontes dfp "
                    "(BPP — demonstrações anuais) e fre (capital social) "
                    "na página Sincronização.")

        kpis: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []

        if eq_ok:
            periods = eq["periods"]           # newest first
            latest = periods[0]
            accounts = latest.get("accounts") or {}
            eq_ref = _fmt_date(latest.get("data_fim_exerc"))

            for code, label, tip in _EQUITY_CODES:
                v = (accounts.get(code) or {}).get("valor_brl")
                kpis.append(kpi(label, fmt_brl(v),
                                f"{tip} — valor de balanço"
                                + (f" (fim de exercício: {eq_ref})."
                                   if eq_ref != "-" else ".")))

            # Chart 1: composition of the latest exercise (static's chart).
            comp_labels = [label for _c, label, _t in _EQUITY_CODES]
            comp_values = [
                round(((accounts.get(c) or {}).get("valor_brl") or 0) / 1e9, 2)
                for c, _l, _t in _EQUITY_CODES]
            if any(v > 0 for v in comp_values):
                sections.append(chart_section(
                    f"Composição do PL ({eq_ref})",
                    {
                        "type": "bar",
                        "data": {
                            "labels": comp_labels,
                            "datasets": [{
                                "label": "R$ bi",
                                "data": comp_values,
                                "backgroundColor": _COLOR_PL,
                                "borderWidth": 0,
                            }],
                        },
                        "options": {"scales": {
                            "y": {"beginAtZero": True, "title": {
                                "display": True, "text": "R$ bi"}},
                            "x": {"ticks": {"maxTicksLimit": 8}},
                        }},
                    },
                    description=(
                        "Componentes do Patrimônio Líquido no último "
                        "exercício (BPP 2.03.*): Capital Social, Reservas, "
                        "Lucros Acumulados e Minority Interest, em R$ "
                        "bilhões. Os componentes não necessariamente somam "
                        "o PL Total (há contas de ajuste fora do recorte)."
                    ),
                ))

            # Chart 2: PL Total + Capital Social over the years.
            chron = list(reversed(periods))
            year_labels = [(p.get("data_fim_exerc") or "")[:4]
                           for p in chron]
            if len(chron) >= 2 and all(year_labels):
                def _bi(p: dict, code: str) -> float | None:
                    v = ((p.get("accounts") or {}).get(code) or {}) \
                        .get("valor_brl")
                    return None if v is None else round(v / 1e9, 2)
                sections.append(chart_section(
                    "Evolução do PL e do Capital Social",
                    {
                        "type": "line",
                        "data": {
                            "labels": year_labels,
                            "datasets": [
                                {"label": "PL Total",
                                 "data": [_bi(p, "2.03") for p in chron],
                                 "borderColor": _COLOR_PL,
                                 "backgroundColor": _COLOR_PL},
                                {"label": "Capital Social",
                                 "data": [_bi(p, "2.03.01") for p in chron],
                                 "borderColor": _COLOR_CAP,
                                 "backgroundColor": _COLOR_CAP},
                            ],
                        },
                        "options": {"scales": {
                            "y": {"beginAtZero": True, "title": {
                                "display": True, "text": "R$ bi"}},
                        }},
                    },
                    description=(
                        "Patrimônio Líquido total (BPP 2.03) e Capital "
                        "Social realizado (BPP 2.03.01) por exercício, em "
                        "R$ bilhões — o PL cresce por lucros retidos "
                        "(reservas), o capital social por emissões."
                    ),
                ))

            # The all-periods table (newest first, compact BRL).
            tbl = table_section(
                "Estrutura Patrimonial (BPP 2.03.*)",
                ["Fim de Exercício"] + [label for _c, label, _t
                                        in _EQUITY_CODES],
                [[_fmt_date(p.get("data_fim_exerc"))]
                 + [fmt_brl(((p.get("accounts") or {}).get(c) or {})
                            .get("valor_brl"))
                    for c, _l, _t in _EQUITY_CODES] for p in periods],
                description=(
                    "Valores de balanço (snapshot) em BRL por exercício — "
                    "Capital Social, Reservas, Lucros Acumulados e "
                    "Minority Interest (DFP anual, meses=12)."
                ),
                note=f"{len(periods)} exercício(s) — DFP, contas BPP 2.03.*.",
            )
            tbl["sortable"] = True
            sections.append(tbl)

        if cap_ok:
            cap_tbl = table_section(
                "Capital Social (FRE)",
                ["Data Referência", "Tipo", "Valor Capital",
                 "Ações ON", "Ações PN", "Ações Totais", "Aprovação"],
                [[_fmt_date(p.get("data_referencia")),
                  p.get("tipo_capital") or "—",
                  fmt_brl(p.get("valor_capital")),
                  fmt_int(p.get("qtd_acoes_on")),
                  fmt_int(p.get("qtd_acoes_pn")),
                  fmt_int(p.get("qtd_acoes_total")),
                  _fmt_date(p.get("data_aprovacao"))]
                 for p in cap["periods"]],
                description=(
                    "Capital social declarado no Formulário de Referência: "
                    "tipo (nominativo etc.), valor e quantidade de ações "
                    "emitidas por classe, com a data da última assembleia "
                    "que aprovou o capital."
                ),
                note=f"{len(cap['periods'])} período(s) — FRE, capital_social.",
            )
            cap_tbl["sortable"] = True
            sections.append(cap_tbl)

        if not kpis:  # only capital data — the KPI grid skips silently
            latest_cap = cap["periods"][0]
            kpis = [
                kpi("Capital Social", fmt_brl(latest_cap.get("valor_capital")),
                    "Capital social realizado (FRE)."),
                kpi("Ações Totais", fmt_int(latest_cap.get("qtd_acoes_total")),
                    "Ações emitidas ON+PN (FRE)."),
            ]

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}
