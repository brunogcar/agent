"""webui/services/indexes.py — Mercado page / Índices family data service (B3).

[v1.14] The Índices family of the ``/webui/mercado`` page — a reorganized
take on the static ``index_dashboard.html`` reference (built by
skills/b3/index/modes/dashboard.py: 6 flat tabs — Resumo + 5 per-index
tabs). Third family of the Mercado page (focus v1.12, fluxo v1.13) —
B3 index compositions from the indexProxy API (5 active indices:
IBOV/SMLL/BDRX/IFIX/IDIV, 26 catalogued).

Per the v1.8–v1.13 reorganization spirit the static's gaps get fixed,
not copied:

  overview → "quais índices acompanhar?"   (KPIs + a tabela de índices
              sincronizados com maior peso e concentração top-5 +
              PRESENÇA EM ÍNDICES — quais tickers estão em 2+ índices,
              cruzamento que o estático não tinha)
  ibov/smll/bdrx/ifix/idiv → "como é a carteira?"  (por índice:
              KPIs + o DOUGHNUT com TODOS os constituintes + o doughnut
              por tipo de ativo + a tabela COMPLETA)

Improvements over the static dashboard:
  - The chart was a BAR of the TOP 15 — every other constituent
    invisible. Now a DOUGHNUT with ALL constituents (one slice each,
    rank order): the ring IS the composition, the tooltip identifies
    each slice, and the full sortable table below is the legend (a
    78-136 entry Chart.js legend would be a wall of labels).
  - The table capped at 20 rows (limit=20) — now lists EVERY
    constituent (user request).
  - Skill-side PT-BR fixes shipped together (helpers v1.1):
    format_pct "10,886%" (was "10.886%"), format_qty "3.535.764.048"
    (was "3,535,764,048"), type "ON NM" (was "ON      NM").
  - NEW: composição por tipo de ativo (ON/PN/UNT/DRN/CI… grouped by
    spec prefix, participation summed) — a second small doughnut.
  - NEW: presença em 2+ índices (the cross-index view the static
    could not answer without flipping 5 tabs).

Every method returns the v1.7 FLAT contract payload
(``{"status": "ok", "kpis"?, "sections"}``) and takes NO ticker — index
composition is market-wide. The adapters registry dispatches these
through the v1.11 ticker-less path and the generic endpoint
``GET /api/webui/mercado/sections/{key}`` serves them; all subtabs
render through the generic renderer (loadIndicesSubtab → valKpisHtml +
valSectionsHtml + mountValCharts in app.js). The big doughnuts ship
``plugins.legend.display=false`` and ``tooltipUnit`` — both honored by
renderValChart since v1.14 (the legend toggle is the cutout/stacked
precedent applied to plugins; the unit formats tooltip values pt-BR).

Data layer = the SAME query engine the skill's static dashboard runs
(read-only; no SQL duplication in the WebUI):
  - ``data_sources.b3.index.query_engine`` (memory_db/b3/index.db —
    index()/summary(), latest composition per index + catalog)

Formatting = the skill's helpers (``skills/b3/index/helpers.py`` —
``format_pct`` table cells "10,886%", ``format_qty`` "3.535.764.048",
``pie_colors`` the deterministic doughnut palette). No forked numerics.

Data conventions (v1.8 fix1 / v1.9–v1.13 lineage):
  - Table dates dd/mm/yyyy. Every number is a PRE-FORMATTED PT-BR
    string — the client only colorizes.
  - Degradation: missing/empty index.db → PT-BR ``_error`` naming the
    ``b3-index`` source exactly as the Sincronização page lists it.
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
from data_sources.b3.index.query_engine import (
    index as _query_index,
    summary as _summary,
)
from data_sources.b3.index.catalog import INDEX_CATALOG

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.b3.index.helpers import (
    clean_type as _fmt_type,         # "ON      NM" → "ON NM"
    format_pct as _fmt_pct,         # "10,886%"
    format_qty as _fmt_qty,         # "3.535.764.048"
    pie_colors as _pie_colors,      # deterministic doughnut palette
)

_ERR = ("Composição de índices indisponível — sincronize a fonte "
        "b3-index (Índices B3) na página Sincronização.")


# ── helpers ─────────────────────────────────────────────────────────────────
def _fmt_date(s: Any) -> Any:
    """ISO YYYY-MM-DD → dd/mm/yyyy (v1.8 fix1 convention; passthrough)."""
    if isinstance(s, str) and len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _snapshot() -> dict[str, Any]:
    """summary() + every active index in ONE call set; ``_error`` on failure.

    Overview and each index view share the same summary-driven error
    path (missing DB, empty sync state); the per-index views re-query
    their own composition lazily.
    """
    try:
        summ = _summary()
    except Exception:
        return {"_error": _ERR}
    if summ.get("status") != "ok":
        return {"_error": _ERR}
    indices = [i for i in summ.get("indices", [])
               if i["active"] and i["constituent_count"] > 0]
    if not indices:
        return {"_error": (
            "Nenhum índice sincronizado — a fonte b3-index sincronizou sem "
            "composições. Rode a sincronização novamente na página "
            "Sincronização.")}
    return {"indices": indices}


def _index_data(code: str) -> dict[str, Any]:
    """query_index(code) with the shared error path."""
    try:
        data = _query_index(code)
    except Exception:
        return {"_error": _ERR}
    if data.get("status") != "ok":
        return {"_error": _ERR}
    if not data.get("constituents"):
        return {"_error": (
            f"O índice {code} sincronizou sem constituintes — rode a "
            "sincronização da fonte b3-index novamente na página "
            "Sincronização.")}
    return data


def _type_groups(constituents: list[dict[str, Any]]) -> list[tuple[str, int, float]]:
    """Group constituents by spec prefix ("ON NM" → "ON"), summed weight.

    Returns [(prefix, count, summed_participation)] sorted by weight.
    """
    groups: dict[str, list[int | float]] = {}
    for c in constituents:
        prefix = _fmt_type(c.get("type")).split(" ")[0] if c.get("type") else "?"
        g = groups.setdefault(prefix, [0, 0.0])
        g[0] += 1
        v = c.get("participation")
        if v is not None:
            g[1] += v
    return sorted(((k, int(v[0]), round(v[1], 3)) for k, v in groups.items()),
                  key=lambda t: t[2], reverse=True)


def _doughnut(title: str, labels: list[str], data: list[float],
              description: str, legend: bool = False,
              cutout: str = "45%") -> dict:
    """Doughnut chart section; legend off for the full-composition ring."""
    cd: dict[str, Any] = {
        "type": "doughnut",
        "data": {"labels": labels, "datasets": [{
            "label": "Participação (%)",
            "data": data,
            "backgroundColor": _pie_colors(len(data)),
            "borderWidth": 1,
        }]},
        "options": {
            "cutout": cutout,
            "plugins": {"legend": {"display": legend}},
            "tooltipUnit": "%",
        },
    }
    return chart_section(title, cd, description=description)


# ── service ─────────────────────────────────────────────────────────────────
class IndexesService:
    """Mercado page / Índices family — 6 subtab payloads (FLAT, no ticker)."""

    # ── Visão Geral ─────────────────────────────────────────────────────────
    def overview(self) -> dict[str, Any]:
        """Quais índices acompanhar — KPIs + índices + presença cruzada.

        Landing subtab (the static's Resumo tab): the GENERAL view — the
        synced indices side by side + which tickers ride in more than one
        (the cross-index comparison the static could not answer without
        flipping 5 tabs). Each index's own composition lives in its subtab.
        """
        snap = _snapshot()
        if "_error" in snap:
            return error_payload("", snap["_error"])

        indices = snap["indices"]
        by_code: dict[str, dict[str, Any]] = {}
        for i in indices:
            by_code[i["code"]] = i

        # Pull each composition once for the cross view + weights.
        comps: dict[str, list[dict[str, Any]]] = {}
        for i in indices:
            data = _index_data(i["code"])
            if "_error" not in data:
                comps[i["code"]] = data["constituents"]

        # Cross-index presence (ticker → indexes).
        presence: dict[str, dict[str, Any]] = {}
        for code, constituents in comps.items():
            for c in constituents:
                p = presence.setdefault(c["ticker"], {
                    "ticker": c["ticker"],
                    "company": c.get("company_name") or "",
                    "indexes": [],
                    "best": (c.get("participation") or 0.0, code),
                })
                p["indexes"].append(code)
                if (c.get("participation") or 0.0) > p["best"][0]:
                    p["best"] = (c.get("participation") or 0.0, code)
        multi = [p for p in presence.values() if len(p["indexes"]) >= 2]
        multi.sort(key=lambda p: (-len(p["indexes"]), -p["best"][0]))

        # KPIs
        total_rows = sum(i["constituent_count"] for i in indices)
        ref_dates = {i["last_date"] for i in indices if i["last_date"]}
        top_overall = max(
            ((c.get("participation") or 0.0, code, c["ticker"])
             for code, cs in comps.items() for c in cs),
            default=None)
        kpis: list[dict[str, Any]] = [
            kpi("Índices ativos", f"{len(indices)}",
                f"{len(INDEX_CATALOG)} índices no catálogo da B3; "
                f"{len(indices)} sincronizados: "
                f"{', '.join(i['code'] for i in indices)}. Ative outros "
                "no catálogo (data_sources/b3/index) para sincronizar."),
            kpi("Data de referência",
                _fmt_date(sorted(ref_dates)[-1]) if ref_dates else "-",
                "Composições vigentes na data — a B3 revisa a carteira dos "
                "índices trimestralmente (o sincronizador busca a vigente)."),
            kpi("Constituintes", f"{total_rows}",
                "Somatório das linhas de composição dos índices "
                "sincronizados (um papel pode figurar em mais de um)."),
            kpi("Em 2+ índices", f"{len(multi)}",
                "Papéis presentes em dois ou mais índices simultaneamente — "
                "a tabela 'Presença em índices' lista todos."),
        ]
        if top_overall:
            w, code, ticker = top_overall
            kpis.append(kpi(
                "Maior peso", f"{ticker}",
                f"{_fmt_pct(w)} no {code} — a maior participação individual "
                "entre todos os índices sincronizados."))

        # Table 1 — synced indices side by side (static's Resumo + weights).
        rows = []
        for i in indices:
            cs = comps.get(i["code"], [])
            top5 = round(sum((c.get("participation") or 0.0)
                             for c in cs[:5]), 3) if cs else None
            top = cs[0] if cs else None
            rows.append([
                i["code"], i["name"], str(i["constituent_count"]),
                f"{top['ticker']} · {_fmt_pct(top.get('participation'))}"
                if top else "-",
                _fmt_pct(top5) if top5 is not None else "-",
                _fmt_date(i["last_date"]) or "-",
            ])
        tbl = table_section(
            "Índices sincronizados",
            ["Código", "Nome", "Constituintes", "Maior peso", "Top 5",
             "Data Ref."],
            rows,
            description=(
                "Os índices ativos no catálogo da B3, lado a lado com o "
                "maior peso individual e a concentração do top 5 — clique "
                "no índice nas sub-abas abaixo para a composição completa."
            ),
            note=("Ativos por padrão: IBOV, SMLL, BDRX, IFIX e IDIV; o "
                  "catálogo da B3 lista 26 — os demais podem ser ativados "
                  "no sincronizador."),
        )
        tbl["sortable"] = True

        # Table 2 — cross-index presence (NEW vs the static).
        cross_rows = [
            [p["ticker"], p["company"], str(len(p["indexes"])),
             " + ".join(p["indexes"]),
             f"{_fmt_pct(p['best'][0])} ({p['best'][1]})"]
            for p in multi
        ]
        cross = table_section(
            "Presença em índices",
            ["Ticker", "Empresa", "Índices", "Quais", "Maior peso"],
            cross_rows,
            description=(
                "Papéis presentes em DOIS ou mais índices sincronizados — "
                "o cruzamento que o dashboard estático não respondia sem "
                "alternar entre as abas de cada índice."
            ),
            note=("Ordenado por nº de índices e maior peso; a composição "
                  "de cada índice individual está na sua sub-aba."),
        )
        cross["sortable"] = True

        return {"status": "ok", "kpis": kpis, "sections": [tbl, cross]}

    # ── Per-index views ─────────────────────────────────────────────────────
    def _view(self, code: str) -> dict[str, Any]:
        """One index: KPIs + full doughnut + type doughnut + full table."""
        data = _index_data(code)
        if "_error" in data:
            return error_payload("", data["_error"])

        constituents = data["constituents"]
        name = data.get("name", code)
        desc = data.get("description", "")
        ref = data.get("ref_date", "")

        # KPIs
        top = constituents[0]
        top5 = round(sum((c.get("participation") or 0.0)
                         for c in constituents[:5]), 3)
        groups = _type_groups(constituents)
        types_txt = " · ".join(f"{g[0]} {g[1]}" for g in groups[:3])
        kpis: list[dict[str, Any]] = [
            kpi("Constituintes", str(len(constituents)),
                f"Composição de {name} vigente em {_fmt_date(ref)}. "
                f"{desc}."),
            kpi("Data de referência", _fmt_date(ref) or "-",
                "Composição vigente — a B3 revisa a carteira "
                "trimestralmente; o sincronizador grava a vigente "
                "(fonte b3-index)."),
            kpi("Maior peso", top["ticker"],
                f"{top.get('company_name') or ''} — "
                f"{_fmt_pct(top.get('participation'))} de peso."),
            kpi("Top 5 — concentração", _fmt_pct(top5),
                "Soma dos pesos dos 5 maiores: "
                + ", ".join(f"{c['ticker']} {_fmt_pct(c.get('participation'))}"
                            for c in constituents[:5]) + "."),
            kpi("Tipos de ativo", types_txt or "-",
                "Pelo prefixo da especificação B3: "
                + ", ".join(f"{g[0]} {g[1]} ({_fmt_pct(g[2])})"
                            for g in groups) + "."),
        ]

        # Chart 1 — the FULL composition doughnut (user request: was top-15 bar).
        labels = [c["ticker"] for c in constituents]
        weights = [c.get("participation") or 0.0 for c in constituents]
        full = _doughnut(
            f"{code} — composição completa",
            labels, weights,
            description=(
                f"TODOS os {len(constituents)} constituintes, uma fatia por "
                "peso (ordem de rank) — o tooltip identifica cada papel. "
                "O gráfico do dashboard estático mostrava apenas o top 15 "
                "em barras; a tabela completa abaixo é a legenda."
            ),
        )

        # Chart 2 — composition by asset type (NEW).
        t_labels = [f"{g[0]} ({g[1]})" for g in groups]
        t_data = [g[2] for g in groups]
        by_type = _doughnut(
            f"{code} — por tipo de ativo",
            t_labels, t_data,
            description=(
                "Peso somado por prefixo da especificação B3 "
                "(ON/PN/UNT para ações, DRN para BDRs, CI para fundos) — "
                "quantidade de papéis entre parênteses."
            ),
            legend=True,
            cutout="55%",
        )

        # Full table — EVERY constituent (user request: was top-20).
        rows = [
            [str(c.get("rank", "")), c["ticker"],
             c.get("company_name") or "", _fmt_type(c.get("type")),
             _fmt_qty(c.get("theorical_qty")),
             _fmt_pct(c.get("participation"))]
            for c in constituents
        ]
        tbl = table_section(
            f"Todos os constituintes ({len(constituents)})",
            ["Rank", "Ticker", "Empresa", "Tipo", "Qtde", "Part. %"],
            rows,
            description=(
                f"A composição INTEIRA de {name} em {_fmt_date(ref)} — o "
                "dashboard estático listava apenas o top 20. Clique no "
                "cabeçalho para ordenar."
            ),
        )
        tbl["sortable"] = True

        return {"status": "ok", "kpis": kpis,
                "sections": [full, by_type, tbl]}

    def ibov(self) -> dict[str, Any]:
        """Ibovespa — a carteira das 78+ maiores da B3."""
        return self._view("IBOV")

    def smll(self) -> dict[str, Any]:
        """Small Cap — menor capitalização com liquidez."""
        return self._view("SMLL")

    def bdrx(self) -> dict[str, Any]:
        """BDRX — BDRs não patrocinados."""
        return self._view("BDRX")

    def ifix(self) -> dict[str, Any]:
        """IFIX — a carteira dos FIIs."""
        return self._view("IFIX")

    def idiv(self) -> dict[str, Any]:
        """IDIV — os maiores pagadores de dividendos."""
        return self._view("IDIV")
