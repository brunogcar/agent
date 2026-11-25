"""webui/services/governance.py — Governança (CGVN).

[v1.26 fix 1] The company page's 11th tab — SPLIT from Informações
Periódicas (the user's verdict: "both provide info, but they are not
supposed to be together, different purpose"). THIS tab is the CGVN
(Código de Melhores Práticas — the practices self-assessment, the
source behind the uploaded PETR4_governance_dashboard.html):

  - overview() → score KPIs + donut + per-chapter bars + the score
    EVOLUTION across filings (the static dashboard only ever showed the
    latest — PETR4 has 9 annual filings); generic contract payload
    (kpis + chart sections — donut/bar/line all render through the ONE
    generic renderer).
  - practices() → the 54-row table with Exercício/Capítulo/Situação
    filters (the static's "Practices"/"By Chapter" tabs folded into one
    filterable view — the Explicação texts are huge, so rows expand on
    click).

The EVENT index (IPE — AGO/AGE, avisos, fatos relevantes) moved to its
OWN tab: webui/services/ipe.py + tab_ipe.html + GET /ipe/events.

Real-data conventions (verified against the user's synced DBs):
  - CGVN adoption has FOUR values (Sim, Não, Parcialmente,
    "Não se Aplica") — the static dashboard's donut counted three;
    the score stays % Sim of total (48/54 = 88,89% for PETR4, matching
    the reference), with N/A shown as its own gray slice.
  - The CGVN label the user reads is the EXERCÍCIO year (ref 2026-12-31
    filing covers exercício 2025) — cgvn.filings() resolves it. The
    LATEST exercício available is ALWAYS last-year-minus-1 relative to
    the filing year: the CVM receives the exercício-2026 protocolos
    during 2027 (cgvn_cia_aberta_2027.zip) — a "missing 2026" is the
    calendar, not a sync gap.
"""
from __future__ import annotations

from typing import Any

# Adoption-value palette (labels in the donut + badges in the table).
ADOPTION_COLORS = {
    "Sim": "#0d9488",            # teal — adopted
    "Parcialmente": "#d97706",   # amber
    "Não": "#dc2626",            # red
    "Não se Aplica": "#64748b",  # gray — out of scope for the company
}


def _compliance_label(score_pct: float) -> str:
    """Alto/Médio/Baixo — the same thresholds the governance skill's
    report.py uses (>=80% Alto, 50-80% Médio, <50% Baixo)."""
    if score_pct >= 0.80:
        return "Alto"
    if score_pct >= 0.50:
        return "Médio"
    return "Baixo"


def _pct(value: float) -> str:
    """0.8889 → '88,89%' (pt-BR, the KPI contract takes formatted strings)."""
    return f"{value * 100:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def _date_br(iso: str) -> str:
    """'2026-06-30' → '30/06/2026'; non-ISO passes through as '-'."""
    if not iso or len(iso) < 10:
        return "-"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


class GovernanceService:
    """The Governança tab's 2 subtab payloads (CGVN only — IPE lives in
    webui/services/ipe.py, its own tab since v1.26 fix 1)."""

    # ── Visão Geral (CGVN) — generic contract payload ─────────────────

    def overview(self, ticker: str) -> dict[str, Any]:
        """Score KPIs + donut + per-chapter bars + score evolution.

        Generic payload: {"ticker", "status", "kpis", "sections"} —
        rendered by the ONE generic renderer (loadGovSubtab →
        valKpisHtml + valSectionsHtml + mountValCharts).
        """
        try:
            from data_sources.cvm.cgvn import query_engine as cgvn
        except Exception as e:  # pragma: no cover — import-time failure
            return self._err(ticker, f"falha ao carregar a fonte cgvn: {e}")

        try:
            score = cgvn.query(company=ticker, score=True)
        except FileNotFoundError:
            return self._err(
                ticker, "Base cgvn não encontrada — sincronize a fonte "
                "cgvn na página Sincronização.")
        except Exception as e:
            return self._err(ticker, f"erro ao consultar cgvn: {e}")

        if score.get("status") != "ok":
            return self._err(
                ticker,
                "Sem dados de governança (CGVN) para este ticker — a "
                "companhia não declara o Código de Melhores Práticas, ou "
                "a fonte cgvn está vazia. Sincronize-a na página "
                "Sincronização.")

        try:
            chapters = cgvn.query(company=ticker, by_chapter=True)
            history = cgvn.filings(company=ticker)
        except Exception:
            chapters = {"status": "error"}
            history = {"status": "error"}

        total = int(score.get("total_practices") or 0)
        sim = int(score.get("adopted_sim") or 0)
        nao = int(score.get("adopted_nao") or 0)
        parcial = int(score.get("adopted_parcialmente") or 0)
        counts = score.get("counts") or {}
        nsa = int(counts.get("Não se Aplica") or 0)
        score_pct = float(score.get("score_pct") or 0.0)

        # The latest filing's document metadata (entrega/exercício/link).
        latest_doc: dict[str, Any] = {}
        if history.get("status") == "ok" and history.get("filings"):
            latest_doc = history["filings"][0]
        exercicio = latest_doc.get("exercicio") or "-"
        entrega = _date_br(latest_doc.get("data_entrega") or "")

        kpis = [
            {"label": "Score de Governança",
             "value": _pct(score_pct),
             "tooltip": "Percentual de práticas adotadas (Sim) no último "
                        "protocolo do Código de Melhores Práticas (CGVN)."},
            {"label": "Práticas", "value": f"{total}",
             "tooltip": "Práticas declaradas no protocolo mais recente."},
            {"label": "Adotadas (Sim)", "value": f"{sim}",
             "tooltip": "Parcialmente e Não se Aplica contam à parte."},
            {"label": "Nível de Conformidade",
             "value": _compliance_label(score_pct),
             "tooltip": "Alto ≥ 80% · Médio 50-80% · Baixo < 50% do score."},
            {"label": "Exercício", "value": str(exercicio),
             "tooltip": "Exercício social coberto pelo último protocolo."},
            {"label": "Entrega", "value": entrega,
             "tooltip": "Data de entrega do protocolo na CVM."},
        ]

        sections: list[dict[str, Any]] = []

        # Donut — four buckets (the static dashboard counted three; the
        # gray N/A slice is honest data the reference dropped).
        sections.append({
            "type": "chart",
            "title": "Adoção das Práticas",
            "description": "Distribuição do último protocolo (CGVN).",
            "chart_data": {
                "type": "doughnut",
                "data": {
                    "labels": ["Sim", "Parcialmente", "Não", "Não se Aplica"],
                    "datasets": [{
                        "data": [sim, parcial, nao, nsa],
                        "backgroundColor": [
                            ADOPTION_COLORS["Sim"],
                            ADOPTION_COLORS["Parcialmente"],
                            ADOPTION_COLORS["Não"],
                            ADOPTION_COLORS["Não se Aplica"]],
                        "borderWidth": 1,
                    }],
                },
                "options": {"cutout": "60%"},
            },
        })

        # Per-chapter stacked bars — the static's "By Chapter" tab.
        if chapters.get("status") == "ok":
            ch_rows = chapters.get("by_chapter") or []
            if ch_rows:
                sections.append({
                    "type": "chart",
                    "title": "Adoção por Capítulo",
                    "description": "Práticas por capítulo no último protocolo "
                                   "(barras empilhadas Sim/Parcialmente/Não).",
                    "chart_data": {
                        "type": "bar",
                        "data": {
                            "labels": [r.get("Capitulo") or "—"
                                       for r in ch_rows],
                            "datasets": [
                                {"label": "Sim",
                                 "data": [r.get("adopted") or 0
                                          for r in ch_rows],
                                 "backgroundColor": ADOPTION_COLORS["Sim"]},
                                {"label": "Parcialmente",
                                 "data": [r.get("partial") or 0
                                          for r in ch_rows],
                                 "backgroundColor":
                                     ADOPTION_COLORS["Parcialmente"]},
                                {"label": "Não",
                                 "data": [r.get("not_adopted") or 0
                                          for r in ch_rows],
                                 "backgroundColor": ADOPTION_COLORS["Não"]},
                            ],
                        },
                        "options": {
                            "scales": {"x": {"stacked": True},
                                       "y": {"stacked": True,
                                             "beginAtZero": True}},
                        },
                    },
                })

        # Score evolution — the interactive bonus the static never had.
        if history.get("status") == "ok":
            fil = [f for f in (history.get("filings") or [])
                   if f.get("exercicio")]
            if len(fil) >= 2:
                fil_asc = sorted(fil, key=lambda f: f["exercicio"])
                sections.append({
                    "type": "chart",
                    "title": "Evolução do Score",
                    "description": "% de práticas adotadas por exercício "
                                   "(protocolos CGVN).",
                    "chart_data": {
                        "type": "line",
                        "data": {
                            "labels": [str(f["exercicio"])
                                       for f in fil_asc],
                            "datasets": [{
                                "label": "Score (% Sim)",
                                "data": [round((f.get("score_pct") or 0)
                                               * 100, 2)
                                         for f in fil_asc],
                                "borderColor": ADOPTION_COLORS["Sim"],
                                "backgroundColor":
                                    "rgba(13,148,136,0.12)",
                                "fill": True,
                                "tension": 0.3,
                            }],
                        },
                        "options": {"tooltipUnit": "%",
                                    "scales": {"y": {"beginAtZero": True,
                                                     "max": 100}}},
                    },
                })

        # Filing ledger — every protocolo with its score + CVM link.
        if history.get("status") == "ok" and history.get("filings"):
            fil = history["filings"]
            rows = [[str(f.get("exercicio") or "-"),
                     _date_br(f.get("data_entrega") or ""),
                     f"{f.get('sim', 0)}/{f.get('total', 0)}",
                     _pct(f.get("score_pct") or 0)]
                    for f in fil]
            sections.append({
                "type": "table",
                "title": "Protocolos CGVN",
                "description": "Um por exercício social. Os links ficam na "
                               "subaba Práticas (coluna Protocolo).",
                "columns": ["Exercício", "Entrega", "Sim/Total", "Score"],
                "rows": rows,
            })

        return {"ticker": ticker.upper(), "status": "ok",
                "kpis": kpis, "sections": sections}

    # ── Práticas (CGVN) — custom payload (filter bar + table) ──────────

    def practices(self, ticker: str, data_ref: str = "", capitulo: str = "",
                  adotada: str = "", q: str = "") -> dict[str, Any]:
        """The 54-practice table for ONE filing + the filings list for
        the Exercício select. Filters applied server-side (the table is
        small — 54 rows — but the selects must reflect the data)."""
        try:
            from data_sources.cvm.cgvn import query_engine as cgvn
        except Exception as e:  # pragma: no cover
            return self._err(ticker, f"falha ao carregar a fonte cgvn: {e}")

        try:
            history = cgvn.filings(company=ticker)
        except FileNotFoundError:
            return self._err(
                ticker, "Base cgvn não encontrada — sincronize a fonte "
                "cgvn na página Sincronização.")
        except Exception as e:
            return self._err(ticker, f"erro ao consultar cgvn: {e}")

        if history.get("status") != "ok" or not history.get("filings"):
            return self._err(
                ticker, "Sem protocolos CGVN para este ticker "
                "(a companhia não declara o Código de Melhores Práticas).")

        filings = history["filings"]

        # data_ref: default = latest; unknown values fall back to latest
        # (a stale select after a re-sync must not 404 the pane).
        refs = {f["data_referencia"] for f in filings}
        if data_ref not in refs:
            data_ref = filings[0]["data_referencia"]
        current = next((f for f in filings
                        if f["data_referencia"] == data_ref), filings[0])

        # Query the SPECIFIC filing (query() is latest-only by design;
        # the Exercício select can point at an older protocolo).
        try:
            conn = cgvn.connect_cgvn(read_only=True)
        except FileNotFoundError:
            return self._err(ticker, "Base cgvn não encontrada.")
        try:
            cnpj = cgvn._resolve_company_cnpj(conn, ticker)
            if not cnpj:
                return self._err(ticker, "companhia não encontrada na base "
                                         "cgvn.")
            params: list[Any] = [cnpj, data_ref]
            conds = ["""REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?""",
                     "Data_Referencia = ?"]
            if capitulo:
                conds.append("Capitulo = ?")
                params.append(capitulo)
            if adotada:
                conds.append("Pratica_Adotada = ?")
                params.append(adotada)
            if q:
                conds.append("(upper(Pratica_Recomendada) LIKE ? OR "
                             "upper(Explicacao) LIKE ? OR upper(ID_Item) "
                             "LIKE ?)")
                like = f"%{q.upper()}%"
                params.extend([like, like, like])
            prow = conn.execute(
                f"""SELECT ID_Item, Capitulo, Principio,
                           Pratica_Recomendada, Pratica_Adotada, Explicacao
                    FROM cgvn_practices
                    WHERE {' AND '.join(conds)}
                    ORDER BY Capitulo, ID_Item""",
                params,
            ).fetchall()
            chapters = [r["Capitulo"] for r in conn.execute(
                """SELECT DISTINCT Capitulo FROM cgvn_practices
                   WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
                     AND Data_Referencia = ?
                   ORDER BY Capitulo""",
                (cnpj, data_ref),
            ).fetchall()]
        finally:
            conn.close()

        return {
            "ticker": ticker.upper(),
            "status": "ok",
            "data_referencia": data_ref,
            "exercicio": current.get("exercicio"),
            "data_entrega": current.get("data_entrega") or "",
            "link": current.get("link") or "",
            "filings": [{
                "data_referencia": f["data_referencia"],
                "exercicio": f.get("exercicio"),
                "score_pct": f.get("score_pct") or 0,
                "sim": f.get("sim", 0),
                "total": f.get("total", 0),
            } for f in filings],
            "capitulos": chapters,
            "adotadas": ["Sim", "Parcialmente", "Não", "Não se Aplica"],
            "filters": {"capitulo": capitulo, "adotada": adotada, "q": q},
            "rows": [{
                "id_item": r["ID_Item"],
                "capitulo": r["Capitulo"] or "",
                "principio": r["Principio"] or "",
                "pratica": r["Pratica_Recomendada"] or "",
                "adotada": r["Pratica_Adotada"] or "",
                "explicacao": r["Explicacao"] or "",
            } for r in prow],
        }

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _err(ticker: str, message: str) -> dict[str, Any]:
        """Canonical error shape — the client renderers show it verbatim."""
        return {"ticker": (ticker or "").upper(), "_error": message}
