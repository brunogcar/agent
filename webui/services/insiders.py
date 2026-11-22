"""webui/services/insiders.py — Insiders tab data service.

[v1.10] The CVM insider-trading view for the company page — a reorganized
take on the static ``PETR4_insider_dashboard.html`` reference (built by
skills/cvm/insider/modes/dashboard.py). Same data layer (VLMO
vlmo_movements — "movimentação de valores mobiliários por administradores
e acionistas relevantes"), but organized around the questions an investor
asks about insider activity, not around the static report's four flat tabs
(its Overview duplicated the identity card + price chart the WebUI already
renders above the tabs):

  overview     → "what are insiders doing?"      (6 KPIs — sentimento,
                 volumes e net dos últimos 24 meses + chart de volume
                 líquido mensal + preview das últimas movimentações)
  transactions → "who moved what, when?"         (tabela completa das
                 últimas N movimentações, sortable + volume líquido
                 acumulado em linha)
  by_role      → "which roles buy vs sell?"      (agregado por cargo +
                 barras comparando volume comprado vs vendido)
  monthly      → "what's the trend?"             (24 meses, tabela +
                 chart de net mensal)

Every method returns the v1.7 FLAT contract payload
(``{"ticker", "status": "ok", "kpis"?, "sections"}``). All subtabs render
through the generic renderer (loadInsSubtab → valKpisHtml + valSectionsHtml
+ mountValCharts in app.js) — no custom client code beyond the loader.

Data conventions (same as v1.8 fix1 / v1.9):
  - Every date the user READS (table cells, prose refs) is dd/mm/yyyy via
    ``_fmt_date``; non-ISO strings pass through so degraded "-" survives.
  - Chart labels ship ISO on purpose — renderValChart detects all-ISO x
    labels and formats ticks + tooltip titles client-side (the cumulative
    chart); the monthly chart labels are BR month labels ("jun/2026" via
    ``_br_month``) and render as-is — ``_valSortKey`` parses that form
    back into chronological order for the table sort.

Window semantics (the static dashboard mixed these silently — here every
table/KPI/note states its window):
  - monthly/overview aggregates: the engine's summary() — LAST 24 MONTHS
    of Data_Movimentacao.
  - transactions table: the engine's history() — the N most recent
    movements (any type: compras, vendas, posse, desligamento...).
  - by_role aggregates: the engine's by_role() — the FULL synced history
    (no date filter), so its counts dwarf the 24-month KPIs by design.

Volume basis: VLMO only fills ``Volume`` for transactions with a declared
unit price (compras/vendas à vista). Posse/desligamento/transferência rows
carry no volume — they still count in "Transações" but contribute R$ 0,00
to the volume aggregates. Tooltips/notes say so where it matters.

Graceful degradation mirrors the skill's contract: a missing vlmo.db (or a
ticker with no movements) returns the canonical ``_error`` payload telling
the user to sync the ``vlmo`` source on the Sincronização page.
"""
from __future__ import annotations

import re as _re
import sys
from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    kpi,
    table_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.cvm.vlmo.query_engine import query as _vlmo_query
from tools.report_ops.formats import fmt_brl, fmt_int

# Palette (same accents as the static dashboard / the rest of the UI).
_COLOR_BUY = "#0d9488"    # teal   — compras / meses de compra líquida
_COLOR_SELL = "#ef4444"   # red    — vendas / meses de venda líquida
_COLOR_CUM = "#3b82f6"    # blue   — linha de volume acumulado

# How many recent movements the transactions subtab renders + feeds the
# cumulative chart with (the static dashboard's cumulative line covered
# only its 10-row table — a window this narrow says nothing about trend).
_TX_CAP = 120

# Insider table preview on the overview subtab (the detail lives in
# Movimentações — same preview→detail pattern as v1.9's top-5).
_TX_PREVIEW = 20

# Movimentação type → PT-BR explanation (tooltips on the Tipo column of
# the transactions tables — mirrors skills/cvm/insider/report.py so the
# vocabulary stays in sync).
_MOVIMENTACAO_TOOLTIPS: dict[str, str] = {
    "compra":        "Compra = aquisição de ações por insider (sentimento positivo).",
    "venda":         "Venda = alienação de ações por insider (sentimento negativo).",
    "doacao":        "Doação = transferência sem contraprestação.",
    "transferencia": "Transferência = movimentação entre contas do mesmo titular.",
    "exercicio":     "Exercício = exercício de opção/bspread de ações.",
    "amortizacao":   "Amortização = amortização de valor de aportes.",
    "posse":         "Posse = início da posição declarada (não é negociação).",
    "desligamento":  "Desligamento/saída = fim do vínculo ou da posição declarada.",
}

_NET_VOLUME_TOOLTIP = (
    "Net Volume = Volume Comprado − Volume Vendido (R$). Positivo = "
    "insiders comprando (sentimento positivo); negativo = insiders vendendo."
)

# [v1.9] ISO date detector — same convention as options.py (v1.8 fix1).
_ISO_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")

# [v1.10] Cargo display cap — chart labels / KPI values (full name stays
# in the table).
_CARGO_CAP = 28


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


def _br_month(s: Any) -> Any:
    """'2026-06' → 'jun/2026' (short PT-BR month).

    Used everywhere the user READS a month — monthly chart labels, the
    Mensal table's Mês column and the Melhor/Pior Mês KPIs. Non-month
    strings pass through so degraded "—" survives. The client's
    _valSortKey parses this form back into chronological order.
    """
    t = str(s or "").strip()
    parts = t.split("-")
    if len(parts) == 2 and len(parts[0]) == 4 and parts[0].isdigit() \
            and parts[1].isdigit():
        mi = int(parts[1])
        if 1 <= mi <= 12:
            names = ["jan", "fev", "mar", "abr", "mai", "jun",
                     "jul", "ago", "set", "out", "nov", "dez"]
            return f"{names[mi - 1]}/{parts[0]}"
    return s


def _log_err(where: str, e: BaseException) -> None:
    print(f"[webui-insiders] {where}: {type(e).__name__}: {e}",
          file=sys.stderr)


def _safe(fn, **kwargs) -> dict:
    """Call the query engine defensively (missing DB → error dict, so one
    broken source degrades sections, never the whole tab)."""
    try:
        return fn(**kwargs)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash the tab
        _log_err(kwargs.get("company", ""), e)
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _trunc(s: str, n: int = _CARGO_CAP) -> str:
    """Truncate long cargo names for chart labels / KPI values."""
    s = (s or "").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


def _movimentacao_tooltip(tipo: Any) -> str:
    """Tooltip for a Tipo_Movimentacao value (fuzzy prefix match)."""
    if not tipo:
        return ""
    key = str(tipo).strip().lower()
    for k, v in _MOVIMENTACAO_TOOLTIPS.items():
        if k in key:
            return v
    return ""


def _is_buy(tipo: Any) -> bool:
    """True for every compra* variant ("Compra", "Compra à vista", ...)."""
    return str(tipo or "").strip().lower().startswith("compra")


def _is_sell(tipo: Any) -> bool:
    """True for every venda* variant ("Venda", "Venda à vista", ...)."""
    return str(tipo or "").strip().lower().startswith("venda")


def _sentiment(bought: float, sold: float) -> str:
    """PT-BR sentiment label over the aggregated volumes (24m window)."""
    if bought > sold:
        return "COMPRANDO"
    if sold > bought:
        return "VENDENDO"
    return "NEUTRO"


class InsiderService:
    """Insiders data service — one method per lazy subtab.

    All queries are read-only SQLite over the synced VLMO DB; no caching
    (single-digit ms queries, lazy per ticker — same policy as
    OptionsService/ShareholdersService).
    """

    # ── shared helpers ────────────────────────────────────────────────────

    def _summary_totals(self, monthly: list[dict]) -> tuple[float, float]:
        """(volume comprado, volume vendido) over the monthly rows."""
        bought = sum(float(m.get("volume_bought") or 0) for m in monthly)
        sold = sum(float(m.get("volume_sold") or 0) for m in monthly)
        return bought, sold

    def _tx_rows(self, movements: list[dict]) -> list[list[Any]]:
        """Transactions table rows — Data | Cargo | Tipo | Ativo | Qtd |
        Preço | Volume. The Tipo cell keeps a tooltip with the movement
        vocabulary (first column carries the date tooltip instead: the
        generic renderer only draws tooltips on the leading cell, so the
        date gets the cargo + tipo context — long cargos truncate)."""
        rows: list[list[Any]] = []
        for m in movements:
            data = m.get("Data_Movimentacao") or "—"
            cargo = m.get("Tipo_Cargo") or "—"
            tipo = m.get("Tipo_Movimentacao") or "—"
            tip = _movimentacao_tooltip(tipo)
            rows.append([
                {"text": _fmt_date(data),
                 "tooltip": f"{cargo} — {tipo}"
                 + (f". {tip}" if tip else "")},
                cargo,
                tipo,
                m.get("Tipo_Ativo") or "—",
                fmt_int(m.get("Quantidade")),
                fmt_brl(m.get("Preco_Unitario"), suffix=False),
                fmt_brl(m.get("Volume")),
            ])
        return rows

    def _tx_table(self, movements: list[dict], title: str,
                  note: str) -> dict[str, Any]:
        sec = table_section(
            title,
            ["Data", "Cargo", "Tipo", "Ativo", "Qtd", "Preço", "Volume"],
            self._tx_rows(movements),
            description=(
                "Movimentações declaradas à CVM por administradores e "
                "acionistas relevantes (VLMO), mais recente primeiro. "
                "\"Posse\"/\"Desligamento\" são eventos de posição — sem "
                "preço nem volume. Volume = Qtd × Preço, quando declarados."
            ),
            note=note,
        )
        sec["sortable"] = True
        return sec

    def _monthly_chart(self, monthly: list[dict]) -> dict[str, Any] | None:
        """Bar chart of net volume per month (teal = compra líquida,
        red = venda líquida), chronological. None when there's nothing
        with a non-null net to draw."""
        chron = list(reversed(monthly))  # engine returns DESC
        labels: list[str] = []
        values: list[float] = []
        colors: list[str] = []
        for m in chron:
            net = m.get("net_volume")
            if net is None:
                continue
            v = float(net)
            labels.append(_br_month(m.get("month")))
            values.append(round(v, 2))
            colors.append(_COLOR_BUY if v >= 0 else _COLOR_SELL)
        if len(labels) < 2:
            return None
        return chart_section(
            "Volume Líquido Mensal (R$)",
            {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": "Net Volume (R$)",
                        "data": values,
                        "backgroundColor": colors,
                        "borderColor": colors,
                        "borderWidth": 1,
                    }],
                },
                "options": {"scales": {
                    "y": {"beginAtZero": True, "title": {
                        "display": True, "text": "R$"}},
                    "x": {"ticks": {"maxTicksLimit": 14}},
                }},
            },
            description=(
                "Compras menos vendas por mês (R$) nos últimos 24 meses. "
                "Barras verdes indicam meses de compra líquida; vermelhas, "
                "meses de venda líquida. Meses com apenas posse/desligamento "
                "aparecem em R$ 0,00."
            ),
        )

    def _cumulative_chart(self, movements: list[dict]) -> dict[str, Any] | None:
        """Cumulative signed volume line over the fetched movements
        (chronological). Only compra*/venda* rows with a Volume count —
        posse/desligamento are not trades. The static dashboard drew this
        over its 10-row table; here it covers the whole fetched window."""
        dated = [m for m in movements if m.get("Data_Movimentacao")]
        dated.sort(key=lambda m: m["Data_Movimentacao"])
        labels: list[str] = []
        cumulative: list[float] = []
        running = 0.0
        for m in dated:
            vol = m.get("Volume")
            if vol is None:
                continue
            try:
                v = float(vol)
            except (TypeError, ValueError):
                continue
            if _is_sell(m.get("Tipo_Movimentacao")):
                running -= v
            elif _is_buy(m.get("Tipo_Movimentacao")):
                running += v
            else:
                continue  # posse/desligamento/doação… — not a trade
            labels.append(m["Data_Movimentacao"])
            cumulative.append(round(running, 2))
        if len(labels) < 2:
            return None
        return chart_section(
            "Volume Líquido Acumulado (R$)",
            {
                "type": "line",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": "Volume acumulado (R$)",
                        "data": cumulative,
                        "borderColor": _COLOR_CUM,
                        "backgroundColor": "rgba(59, 130, 246, 0.15)",
                        "fill": True,
                    }],
                },
                "options": {"scales": {
                    "y": {"title": {"display": True, "text": "R$"}},
                }},
            },
            description=(
                "Soma acumulada das movimentações com preço declarado na "
                "janela exibida (compras somam, vendas subtraem). É o "
                "equilíbrio líquido dos insiders ao longo do tempo — a "
                "inclinação da linha é o sentimento."
            ),
        )

    # ── 1/4: Visão Geral ──────────────────────────────────────────────────

    def overview(self, ticker: str) -> dict[str, Any]:
        """The insider activity state on one screen.

        6 KPI cards (Sentimento / Volume Comprado / Volume Vendido / Net
        Volume / Transações / Última Movimentação — the last-24-months
        aggregates) + the monthly net chart + the last-20 transactions
        preview (the detail lives in Movimentações).
        """
        tk = (ticker or "").upper()
        summ = _safe(_vlmo_query, company=tk, summary=True)
        hist = _safe(_vlmo_query, company=tk, limit=_TX_PREVIEW)

        monthly = summ.get("monthly") if summ.get("status") == "ok" else None
        movements = hist.get("movements") if hist.get("status") == "ok" else None

        if not monthly and not movements:
            return error_payload(
                tk, "Sem movimentações de insiders — sincronize a fonte "
                    "vlmo (CVM — movimentação de valores mobiliários por "
                    "administradores) na página Sincronização.")

        kpis: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []

        if monthly:
            bought, sold = self._summary_totals(monthly)
            net = bought - sold
            tx_count = sum(int(m.get("transaction_count") or 0)
                           for m in monthly)
            window = (f"{monthly[-1].get('month')} a "
                      f"{monthly[0].get('month')}") if len(monthly) > 1 \
                else str(monthly[0].get("month"))
            kpis = [
                kpi("Sentimento (24m)", _sentiment(bought, sold),
                    "Insiders comprando ou vendendo, pela comparação dos "
                    f"volumes declarados na janela de {window}. Contabiliza "
                    "apenas transações com preço declarado (compras/vendas); "
                    "posse e desligamento não têm volume."),
                kpi("Volume Comprado (24m)", fmt_brl(bought),
                    "Total comprado pelos insiders na janela de 24 meses "
                    "(transações com preço declarado)."),
                kpi("Volume Vendido (24m)", fmt_brl(sold),
                    "Total vendido pelos insiders na janela de 24 meses "
                    "(transações com preço declarado)."),
                kpi("Net Volume (24m)", fmt_brl(net),
                    _NET_VOLUME_TOOLTIP + " Janela de 24 meses."),
                kpi("Transações (24m)", fmt_int(tx_count),
                    "Movimentações declaradas na janela de 24 meses — "
                    "inclui posse, desligamento e transferências (sem "
                    "volume), por isso pode exceder o número de negociações "
                    "com preço."),
            ]
            chart = self._monthly_chart(monthly)
            if chart:
                sections.append(chart)
        else:
            kpis = [
                kpi("Sentimento (24m)", "—",
                    "Sem agregação mensal (datas de movimentação ausentes "
                    "na base VLMO sincronizada)."),
            ]

        # Última movimentação — from the newest history row (falls back to
        # the newest monthly label when history came back empty).
        last_mv = "—"
        last_tip = "Sem movimentações na base VLMO."
        if movements:
            m0 = movements[0]
            last_mv = _fmt_date(m0.get("Data_Movimentacao"))
            last_tip = (f"{m0.get('Tipo_Movimentacao') or '—'} — "
                        f"{m0.get('Tipo_Cargo') or '—'} · "
                        f"{fmt_int(m0.get('Quantidade'))} "
                        f"{m0.get('Tipo_Ativo') or ''}"
                        + (f" · {fmt_brl(m0.get('Volume'))}"
                           if m0.get("Volume") is not None else ""))
        elif monthly:
            last_mv = str(monthly[0].get("month") or "—")
            last_tip = "Mês mais recente com movimentações declaradas."
        kpis.append(kpi("Última Movimentação", last_mv, last_tip))

        if movements:
            sections.append(self._tx_table(
                movements[:_TX_PREVIEW],
                f"Últimas Movimentações ({min(len(movements), _TX_PREVIEW)})",
                "Preview — a lista completa e o volume acumulado estão na "
                "subaba Movimentações."))
        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 2/4: Movimentações ────────────────────────────────────────────────

    def transactions(self, ticker: str) -> dict[str, Any]:
        """The full recent-transactions table + the cumulative net line.

        The static dashboard capped this at 10 rows and drew its
        cumulative line over those 10 points; here the window is the
        last 120 movements (sortable, and the note says the real count).
        """
        tk = (ticker or "").upper()
        res = _safe(_vlmo_query, company=tk, limit=_TX_CAP)
        movements = res.get("movements") if res.get("status") == "ok" else None
        if not movements:
            return error_payload(
                tk, "Sem movimentações de insiders — sincronize a fonte "
                    "vlmo (CVM — movimentação de valores mobiliários por "
                    "administradores) na página Sincronização.")

        dated = [m.get("Data_Movimentacao") for m in movements
                 if m.get("Data_Movimentacao")]
        first = _fmt_date(min(dated)) if dated else "—"
        last = _fmt_date(max(dated)) if dated else "—"
        net = 0.0
        for m in movements:
            vol = m.get("Volume")
            if vol is None:
                continue
            try:
                v = float(vol)
            except (TypeError, ValueError):
                continue
            if _is_sell(m.get("Tipo_Movimentacao")):
                net -= v
            elif _is_buy(m.get("Tipo_Movimentacao")):
                net += v

        kpis = [
            kpi("Movimentações", fmt_int(len(movements)),
                f"As {_TX_CAP} movimentações mais recentes declaradas à "
                "CVM por administradores e acionistas relevantes da "
                "companhia."),
            kpi("Primeira", first,
                "Data da movimentação mais antiga na janela exibida."),
            kpi("Última", last,
                "Data da movimentação mais recente na janela exibida."),
            kpi("Net Volume (janela)", fmt_brl(net),
                _NET_VOLUME_TOOLTIP + " Calculado sobre as movimentações "
                "exibidas nesta tabela (não sobre todo o histórico)."),
        ]

        cumulative = self._cumulative_chart(movements)
        sections = []
        if cumulative:
            sections.append(cumulative)
        sections.append(self._tx_table(
            movements,
            f"Movimentações de Insiders ({len(movements)})",
            f"{len(movements)} movimentações (máx. {_TX_CAP}) — VLMO, "
            "ordenadas por data, mais recente primeiro."))

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 3/4: Por Cargo ────────────────────────────────────────────────────

    def by_role(self, ticker: str) -> dict[str, Any]:
        """Insider activity aggregated by role (Tipo_Cargo) + the grouped
        buy-vs-sell bar chart.

        [fix] The engine now aggregates by Tipo_Movimentacao prefix, so
        \"Compra à vista\"/\"Venda à vista\" rows count — the static
        dashboard's table summed only plain \"Compra\"/\"Venda\" and its
        Net Volume column shipped raw floats (6631314.28…). Both fixed
        here: same engine, fmt_brl formatting.
        """
        tk = (ticker or "").upper()
        res = _safe(_vlmo_query, company=tk, by_role=True, limit=30)
        roles = res.get("by_role") if res.get("status") == "ok" else None
        if not roles:
            return error_payload(
                tk, "Sem movimentações de insiders — sincronize a fonte "
                    "vlmo (CVM — movimentação de valores mobiliários por "
                    "administradores) na página Sincronização.")

        enriched: list[dict[str, Any]] = []
        for r in roles:
            vb = float(r.get("volume_bought") or 0)
            vs = float(r.get("volume_sold") or 0)
            enriched.append({
                "cargo": r.get("Tipo_Cargo") or "—",
                "count": int(r.get("transaction_count") or 0),
                "qtd_bought": r.get("total_bought"),
                "qtd_sold": r.get("total_sold"),
                "vol_bought": vb,
                "vol_sold": vs,
                "net": vb - vs,
                "first": r.get("earliest_date"),
                "last": r.get("latest_date"),
            })

        most_active = max(enriched, key=lambda r: r["count"])
        best_buyer = max(enriched, key=lambda r: r["net"])
        best_seller = min(enriched, key=lambda r: r["net"])

        kpis = [
            kpi("Cargos", fmt_int(len(enriched)),
                "Cargos distintos com movimentações declaradas "
                "(Tipo_Cargo) em todo o histórico sincronizado."),
            kpi("Cargo Mais Ativo", _trunc(most_active["cargo"]),
                f"{most_active['cargo']} — {fmt_int(most_active['count'])} "
                "movimentações declaradas (todo o histórico)."),
            kpi("Maior Comprador Líquido",
                _trunc(best_buyer["cargo"]) if best_buyer["net"] > 0 else "—",
                (f"{best_buyer['cargo']} — net {fmt_brl(best_buyer['net'])} "
                 "(volume comprado − vendido, todo o histórico).")
                if best_buyer["net"] > 0 else
                "Nenhum cargo com compras líquidas no histórico sincronizado."),
            kpi("Maior Vendedor Líquido",
                _trunc(best_seller["cargo"]) if best_seller["net"] < 0 else "—",
                (f"{best_seller['cargo']} — net {fmt_brl(best_seller['net'])} "
                 "(volume vendido − comprado, todo o histórico).")
                if best_seller["net"] < 0 else
                "Nenhum cargo com vendas líquidas no histórico sincronizado."),
        ]

        tbl = table_section(
            f"Movimentações por Cargo ({len(enriched)})",
            ["Cargo", "Transações", "Qtd Comprada", "Qtd Vendida",
             "Vol Comprado", "Vol Vendido", "Net Volume"],
            [[r["cargo"], fmt_int(r["count"]),
              fmt_int(r["qtd_bought"]), fmt_int(r["qtd_sold"]),
              fmt_brl(r["vol_bought"]), fmt_brl(r["vol_sold"]),
              fmt_brl(r["net"])] for r in enriched],
            description=(
                "Movimentações agrupadas por cargo (Tipo_Cargo) em TODO o "
                "histórico sincronizado — por isso as contagens superam as "
                "da visão de 24 meses. \"—\" = cargo não declarado no "
                "formulário. Net Volume positivo = cargo comprador líquido."
            ),
            note="VLMO, agregado por Tipo_Cargo (compra*/venda* por prefixo).",
        )
        tbl["sortable"] = True

        sections = [tbl]

        # Grouped bar chart — buy vs sell volume per cargo (chart labels
        # truncate; the table carries the full names).
        labels = [_trunc(r["cargo"]) for r in enriched]
        bought = [round(r["vol_bought"], 2) for r in enriched]
        sold = [round(r["vol_sold"], 2) for r in enriched]
        if any(v > 0 for v in bought) or any(v > 0 for v in sold):
            sections.append(chart_section(
                "Volume Comprado vs Vendido por Cargo (R$)",
                {
                    "type": "bar",
                    "data": {
                        "labels": labels,
                        "datasets": [
                            {"label": "Vol Comprado",
                             "data": bought,
                             "backgroundColor": _COLOR_BUY},
                            {"label": "Vol Vendido",
                             "data": sold,
                             "backgroundColor": _COLOR_SELL},
                        ],
                    },
                    "options": {"scales": {
                        "y": {"beginAtZero": True, "title": {
                            "display": True, "text": "R$"}},
                        "x": {"ticks": {"maxTicksLimit": 8}},
                    }},
                },
                description=(
                    "Volume comprado (verde) vs vendido (vermelho) por "
                    "cargo, em TODO o histórico sincronizado. Cargos com "
                    "barras verdes maiores são compradores líquidos; "
                    "vermelhas maiores, vendedores líquidos."
                ),
            ))

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 4/4: Mensal ───────────────────────────────────────────────────────

    def monthly(self, ticker: str) -> dict[str, Any]:
        """Monthly net buy/sell table + chart (last 24 months)."""
        tk = (ticker or "").upper()
        summ = _safe(_vlmo_query, company=tk, summary=True)
        monthly = summ.get("monthly") if summ.get("status") == "ok" else None
        if not monthly:
            return error_payload(
                tk, "Sem movimentações de insiders — sincronize a fonte "
                    "vlmo (CVM — movimentação de valores mobiliários por "
                    "administradores) na página Sincronização.")

        buyers = [m for m in monthly if (m.get("net_volume") or 0) > 0]
        sellers = [m for m in monthly if (m.get("net_volume") or 0) < 0]
        best = max(monthly, key=lambda m: m.get("net_volume") or 0)
        worst = min(monthly, key=lambda m: m.get("net_volume") or 0)

        kpis = [
            kpi("Meses", fmt_int(len(monthly)),
                "Meses com movimentações declaradas (janela de 24 meses)."),
            kpi("Meses Compradores", fmt_int(len(buyers)),
                "Meses com net volume positivo (insiders comprando) na "
                "janela."),
            kpi("Meses Vendedores", fmt_int(len(sellers)),
                "Meses com net volume negativo (insiders vendendo) na "
                "janela."),
            kpi("Melhor Mês", _br_month(best.get("month")),
                f"{_br_month(best.get('month'))} — net "
                f"{fmt_brl(best.get('net_volume'))} "
                "(maior compra líquida mensal da janela)."),
            kpi("Pior Mês", _br_month(worst.get("month")),
                f"{_br_month(worst.get('month'))} — net "
                f"{fmt_brl(worst.get('net_volume'))} "
                "(maior venda líquida mensal da janela)."),
        ]

        tbl = table_section(
            f"Compra/Venda Líquida por Mês ({len(monthly)} meses)",
            ["Mês", "Transações", "Qtd Comprada", "Qtd Vendida",
             "Vol Comprado", "Vol Vendido", "Net Volume"],
            [[_br_month(m.get("month")),
              fmt_int(m.get("transaction_count")),
              fmt_int(m.get("bought")), fmt_int(m.get("sold")),
              fmt_brl(m.get("volume_bought")),
              fmt_brl(m.get("volume_sold")),
              fmt_brl(m.get("net_volume"))] for m in monthly],
            description=(
                "Resumo mensal das movimentações (janela de 24 meses). "
                "\"Transações\" conta todas as movimentações — inclusive "
                "posse/desligamento, que não têm quantidade nem volume; "
                "por isso meses com R$ 0,00 podem exibir transações."
            ),
            note="VLMO, agregado por mês de Data_Movimentacao.",
        )
        tbl["sortable"] = True

        chart = self._monthly_chart(monthly)
        sections = [chart, tbl] if chart else [tbl]

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}
