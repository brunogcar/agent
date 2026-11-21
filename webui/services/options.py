"""webui/services/options.py — Opções tab data service.

[v1.8] The B3 options view for the company page — a reorganized take on
the static ``PETR4_options_dashboard.html`` reference (which was built by
skills/b3/options/modes/dashboard.py). Same data layer (cotahist_derivatives
+ derivatives.db + instruments.db + SGS Selic + Black-Scholes IV), but
organized around the questions an options investor asks, not around the
six flat tabs of the static report:

  overview   → "where does the options market stand?"  (KPIs + P/C chart)
  chain      → "what's quoted?"   (maturity pills + Calls|Puts side by side)
  activity   → "what's trading / being exercised?"
  iv         → "what does the market price?"  (smile + term structure)
  positions  → "who's positioned where?"  (OI walls + coverage)

Every method returns the v1.7 FLAT contract payload
(``{"ticker", "status": "ok", "kpis"?, "sections", "maturities"?,
"active_maturity"?}``). ``maturities``/``active_maturity`` are extra keys
the contract validator ignores — the client (renderOptSubtab) reads them
to draw the maturity pill bar and refetch with ``?maturity=YYYY-MM-DD``.

Graceful degradation mirrors the skill's contract: a missing DB drops just
the sections that need it (open_positions KPIs become "-", the OI columns
show "-"); total failure (no cotahist_derivatives at all) returns the
canonical ``_error`` payload telling the user which source to sync.
"""
from __future__ import annotations

import datetime as _dt
import re as _re
from typing import Any

from webui.adapters.contract import (
    chart_section,
    error_payload,
    kpi,
    table_section,
)

# ── the skill's data layer (single source of truth — same queries the
#    static dashboard runs; no SQL duplication in the WebUI) ─────────────────
from data_sources.b3.cotahist.derivatives_query import (
    available_maturities,
    exercise_summary,
    options_chain,
    put_call_ratio,
    volume_by_strike,
)
from data_sources.b3.api.query_engine import open_positions as _open_positions
from skills.b3.options.helpers import (
    format_brl,
    format_int,
    format_pct,
    format_value,
)
# Black-Scholes inputs + IV engine (imported from the skill — private names,
# but stable within the repo; duplicating the Selic/spot/IV plumbing here
# would fork the numerics).
from skills.b3.options.modes.dashboard import (  # noqa: PLC2701 — see above
    _compute_iv_for_option,
    _fetch_selic_rate,
    _fetch_spot_price,
    _iv_color,
    _iv_text_color,
)

# Accent colors (same palette as the static dashboard / the rest of the UI).
_COLOR_CALL = "#22c55e"   # green — calls
_COLOR_PUT = "#ef4444"    # red   — puts
_COLOR_REF = "#9ca3af"    # gray  — reference line at 1.0
_COLOR_RATIO = "#3b82f6"  # blue  — P/C ratio line

# Chain tables: top-N rows by volume (the static dashboard dumps every
# row — 151 calls + 124 puts straight into a 3.2 MB HTML file; the WebUI
# caps + lets the user sort). Positions tables: top-N by open interest.
_CHAIN_CAP = 30
_POS_CAP = 50

# Term-structure heatmap caps: strikes within ±25% of spot and the nearest
# 8 future expiries (the static version renders 615×291 — unreadable).
_HEAT_STRIKE_WINDOW = 0.25
_HEAT_MATURITY_CAP = 8

# Maturity pill bar cap: B3 lists monthlies + weeklies (PETR has ~290
# distinct expiries) — the bar shows only the nearest futures.
_MATURITY_PILL_CAP = 12


# [v1.8 fix1] ISO date detector — "2026-09-18" style strings only.
_ISO_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fmt_date(s: Any) -> Any:
    """ISO "2026-09-18" → "18/09/2026" (padrão brasileiro).

    Used for every date the user READS: table cells (Data / Vencimento
    columns) and prose refs ("ref: …", "vencimento …"). Anything that isn't
    an ISO date (None, "-", "", already formatted) passes through
    untouched so the degraded paths keep their placeholders.

    Chart labels are the ONE deliberate exception — they ship ISO on
    purpose: renderValChart detects all-ISO labels and formats the axis
    ticks + tooltip titles client-side (v1.8 fix1), the same fmtDate
    convention as every other chart in the app. Keeping the payload ISO
    also keeps valChartRange's label slicing trivial.
    """
    if isinstance(s, str) and _ISO_DATE_RE.match(s):
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def _log_err(where: str, e: BaseException) -> None:
    print(f"[webui-options] {where}: {type(e).__name__}: {e}",
          file=__import__("sys").stderr)


def _safe(fn, **kwargs) -> dict:
    """Call a query-engine function defensively (same normalization the
    skill's dashboard uses: any failure → {"status": "error", "error": …}
    so one broken DB degrades sections, never the whole tab)."""
    try:
        return fn(**kwargs)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash the tab
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _underlying(ticker: str) -> str:
    """PETR4 / petr → PETR (4-letter underlying code)."""
    t = (ticker or "").upper().rstrip("0123456789")
    return t if len(t) >= 4 else (ticker or "").upper()


def _err_section(title: str, message: str) -> dict[str, Any]:
    """A visible-but-graceful "this piece is unavailable" block — a table
    section with the message as description (the contract has no error
    section type; an empty-looking render hides problems, this doesn't)."""
    return table_section(title, ["—"], [["—"]], description=message)


class OptionsService:
    """Opções data service — one method per lazy subtab.

    All queries are read-only SQLite against the synced DBs; no caching
    (the queries are single-digit ms on the derivatives tables and the
    tab is lazy-loaded per ticker).
    """

    # ── shared helpers ────────────────────────────────────────────────────

    def _maturity_pills(self, u: str) -> tuple[list[str], str]:
        """Future expiries for the pill bar + the default (nearest).

        Returns (maturities, active). Empty list when the DB has none —
        callers then omit the pill bar entirely.
        """
        res = _safe(available_maturities, underlying=u)
        if res.get("status") != "ok":
            return [], ""
        today = _dt.date.today().isoformat()
        mats = sorted({m["maturity"] for m in res.get("maturities", [])
                       if m.get("maturity") and m["maturity"] >= today})
        if not mats:  # all expired (stale sync) → fall back to the last one
            all_m = sorted({m["maturity"] for m in res.get("maturities", [])
                            if m.get("maturity")})
            return (all_m[-1:], all_m[0]) if all_m else ([], "")
        return mats[:_MATURITY_PILL_CAP], mats[0]

    @staticmethod
    def _fmt_mat(m: str) -> str:
        """2026-09-18 → 18/09/26 (compact pill + heatmap header)."""
        try:
            return _dt.date.fromisoformat(m).strftime("%d/%m/%y")
        except ValueError:
            return m

    def _pc_chart(self, obs: list[dict]) -> dict[str, Any]:
        """The dual-axis Put/Call chart config (calls/puts bars on y,
        P/C ratio line on y1, dashed reference at 1.0)."""
        labels = [o["ref_date"] for o in obs]
        return {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Volume Calls", "type": "bar",
                        "data": [o.get("call_volume", 0) or 0 for o in obs],
                        "backgroundColor": _COLOR_CALL,
                        "yAxisID": "y", "order": 3, "borderWidth": 0,
                    },
                    {
                        "label": "Volume Puts", "type": "bar",
                        "data": [o.get("put_volume", 0) or 0 for o in obs],
                        "backgroundColor": _COLOR_PUT,
                        "yAxisID": "y", "order": 2, "borderWidth": 0,
                    },
                    {
                        "label": "P/C Ratio", "type": "line",
                        "data": [o.get("ratio") for o in obs],
                        "borderColor": _COLOR_RATIO,
                        "backgroundColor": _COLOR_RATIO,
                        "yAxisID": "y1", "order": 1,
                        "pointRadius": 0, "pointHoverRadius": 3,
                        "borderWidth": 1.5, "tension": 0.2,
                    },
                    {
                        "label": "Referência (1,0)", "type": "line",
                        "data": [1.0] * len(labels),
                        "borderColor": _COLOR_REF,
                        "borderDash": [6, 4], "borderWidth": 1.2,
                        "yAxisID": "y1", "order": 0,
                        "pointRadius": 0,
                    },
                ],
            },
            "options": {
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"beginAtZero": True, "position": "left",
                          "title": {"display": True, "text": "Volume (R$)"}},
                    "y1": {"position": "right", "beginAtZero": True,
                           "grid": {"drawOnChartArea": False},
                           "title": {"display": True, "text": "P/C Ratio"}},
                },
            },
        }

    # ── 1/5: Visão Geral ──────────────────────────────────────────────────

    def overview(self, ticker: str) -> dict[str, Any]:
        """The empty-KPI-grid fix: the market's state on one screen.

        6 KPI cards (Spot / Próx. Vencimento / OI Total / P/C hoje /
        Call-Put OI / Cobertura) + the 90-pregões P/C chart (range bar) +
        Últimas Observações paired with Resumo CALL vs PUT.
        """
        tk = (ticker or "").upper()
        u = _underlying(tk)
        sections: list[dict[str, Any]] = []
        kpis: list[dict[str, Any]] = []

        # Spot (cotahist equities) — everything degrades around it.
        spot, spot_ref = None, None
        try:
            spot, spot_ref = _fetch_spot_price(u)
        except Exception as e:  # noqa: BLE001
            _log_err("overview spot", e)

        # P/C ratio (90 pregões) — the chart + today's KPI.
        pc = _safe(put_call_ratio, underlying=u, days=90)
        pc_ok = pc.get("status") == "ok" and pc.get("observations")
        obs = (pc.get("observations") or []) if pc_ok else []

        # Open positions (derivatives.db) — OI KPIs + CALL vs PUT resumo.
        op = _safe(_open_positions, underlying=u)
        op_ok = op.get("status") == "ok"
        summary = op.get("summary", {}) if op_ok else {}
        by_strike = op.get("by_strike", []) if op_ok else []
        op_ref = op.get("refdate", "-") if op_ok else "-"

        call_sum = summary.get("CALL", {}) or {}
        put_sum = summary.get("PUT", {}) or {}
        total_oi = (call_sum.get("oi", 0) or 0) + (put_sum.get("oi", 0) or 0)
        call_oi = call_sum.get("oi", 0) or 0
        put_oi = put_sum.get("oi", 0) or 0
        cp_oi = (put_oi / call_oi) if call_oi > 0 else None
        ttl = (call_sum.get("total", 0) or 0) + (put_sum.get("total", 0) or 0)
        cov = (call_sum.get("covered", 0) or 0) + (put_sum.get("covered", 0) or 0)
        cov_pct = (cov / ttl * 100.0) if ttl > 0 else None

        # Next maturity + days to expiry.
        mats, active = self._maturity_pills(u)
        days_to = ""
        if active:
            try:
                days_to = str((_dt.date.fromisoformat(active)
                               - _dt.date.today()).days)
            except ValueError:
                days_to = ""

        if not pc_ok and not op_ok and spot is None:
            return error_payload(
                tk, "Sem dados de opções — sincronize a fonte b3_cotahist "
                    "(derivativos) e b3_derivatives (posições abertas).")

        # ── KPI cards ─────────────────────────────────────────────────
        kpis = [
            kpi("Spot", format_brl(spot) if spot is not None else "-",
                f"Último fechamento do ativo-objeto no cotahist"
                + (f" (ref: {_fmt_date(spot_ref)})" if spot_ref else "")),
            kpi("Próx. Vencimento",
                (self._fmt_mat(active) + (f" · {days_to}d" if days_to else ""))
                if active else "-",
                "Vencimento mais próximo com opções listadas (dias corridos "
                "até o vencimento)."),
            kpi("P/C Ratio (volume)",
                format_value(obs[-1].get("ratio"), "ratio") if obs else "-",
                "Volume de puts / volume de calls no último pregão. "
                "> 1 = bearish (mais puts); < 1 = bullish (mais calls)."),
            kpi("OI Total",
                format_int(total_oi) if op_ok else "-",
                "Interesse aberto somado (calls + puts), do derivatives.db "
                f"(ref: {_fmt_date(op_ref)})."),
            kpi("Call/Put OI",
                format_value(cp_oi, "ratio") if cp_oi is not None else "-",
                "OI de puts / OI de calls. > 1 = mais posições em puts "
                "(bearish); < 1 = mais em calls (bullish)."),
            kpi("Cobertura",
                format_pct(cov_pct / 100.0) if cov_pct is not None else "-",
                "Posições cobertas (com lastro em ação) / total de posições."),
        ]

        # ── P/C chart + últimas observações ───────────────────────────
        if obs:
            sections.append(chart_section(
                f"Put/Call Ratio — {u}",
                self._pc_chart(obs),
                description=(
                    "Volume de calls (verde) + puts (vermelho) no eixo "
                    "esquerdo + razão P/C (azul) no direito. 90 pregões. "
                    "Ratio > 1,0 = bearish (mais puts); < 1,0 = bullish "
                    "(mais calls). Linha tracejada cinza = referência 1,0."
                ),
                # extra key: the client adds the Tudo/…/1M range bar
                # and filters client-side from chart_data (v1.7.2 pattern).
            ))
            sections[-1]["price_range_selector"] = True

            last15 = list(reversed(obs))[:15]
            obs_sec = table_section(
                f"Últimas Observações — {u}",
                ["Data", "Vol. Calls (R$)", "Vol. Puts (R$)", "P/C Ratio"],
                [[_fmt_date(o["ref_date"]), format_int(o.get("call_volume", 0)),
                  format_int(o.get("put_volume", 0)),
                  format_value(o.get("ratio"), "ratio")] for o in last15],
                description="Últimas 15 observações diárias (mais recente "
                            "primeiro).",
            )
            obs_sec["sortable"] = True
            if op_ok:
                obs_sec["pair_with_next"] = True  # side by side w/ resumo
            sections.append(obs_sec)

        # ── Resumo CALL vs PUT (promoted from the bottom of the static
        #    tab 6 — it answers "who's positioned" in one glance) ──────
        if op_ok:
            resumo_rows = [
                [ot,
                 format_int((summary.get(ot) or {}).get("covered", 0)),
                 format_int((summary.get(ot) or {}).get("blocked", 0)),
                 format_int((summary.get(ot) or {}).get("uncovered", 0)),
                 format_int((summary.get(ot) or {}).get("total", 0)),
                 format_int((summary.get(ot) or {}).get("holders", 0)),
                 format_int((summary.get(ot) or {}).get("writers", 0))]
                for ot in ("CALL", "PUT")
            ]
            sections.append(table_section(
                f"Resumo CALL vs PUT — {u}",
                ["Tipo", "Coberta", "Travada", "Descoberta", "Total",
                 "Titulares", "Lançadores"],
                resumo_rows,
                description=(
                    f"Comparação CALL vs PUT (ref: {_fmt_date(op_ref)}). Coberta = "
                    "lastro em ação (covered); Travada = garantia em "
                    "cash/bloqueada (locked); Descoberta = sem lastro "
                    "(naked). Titulares = compradores; Lançadores = "
                    "vendedores."
                ),
            ))
        elif obs:
            sections.append(_err_section(
                f"Posições em Aberto — {u}",
                "derivatives.db indisponível — sincronize a fonte "
                "b3_derivatives para ver o resumo de posições (OIs, "
                "cobertura, titulares/lançadores)."))

        # OI walls chart — the single most useful positions visual, cheap
        # to add here and it belongs on the overview.
        if by_strike:
            sections.append(chart_section(
                f"Interesse Aberto por Strike — {u}",
                {
                    "type": "bar",
                    "data": {
                        "labels": [format_brl(s.get("strike"))
                                   for s in by_strike],
                        "datasets": [
                            {"label": "OI Calls", "data":
                             [s.get("call_oi", 0) for s in by_strike],
                             "backgroundColor": _COLOR_CALL,
                             "borderWidth": 0},
                            {"label": "OI Puts", "data":
                             [s.get("put_oi", 0) for s in by_strike],
                             "backgroundColor": _COLOR_PUT,
                             "borderWidth": 0},
                        ],
                    },
                    "options": {"scales": {
                        "x": {"ticks": {"maxTicksLimit": 25}},
                        "y": {"beginAtZero": True, "title": {
                            "display": True,
                            "text": "Open Interest (contratos)"}},
                    }},
                },
                description=(
                    f"Open Interest por strike (ref: {_fmt_date(op_ref)}). Barras verdes "
                    "= calls; vermelhas = puts. Concentrações de OI indicam "
                    "'paredões' de suporte (puts) ou resistência (calls)."
                ),
            ))

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}

    # ── 2/5: Cadeia ───────────────────────────────────────────────────────

    def chain(self, ticker: str, maturity: str = "") -> dict[str, Any]:
        """The full quote ladder — maturity pills + Calls|Puts side by side.

        The static dashboard hard-locked the nearest expiry; here every
        future expiry is one pill click away (server refetch). Tables cap
        at the top 30 by volume (the note shows the real total — the
        static file shipped all 275 rows into the DOM).
        """
        tk = (ticker or "").upper()
        u = _underlying(tk)

        mats, default_mat = self._maturity_pills(u)
        active = maturity if maturity in mats else default_mat

        res = _safe(options_chain, underlying=u, maturity=active)
        if res.get("status") != "ok":
            return error_payload(
                tk, "Sem dados de opções — sincronize a fonte b3_cotahist "
                    f"({res.get('error', 'sem cadeia para ' + u)}).")

        options = res.get("options", [])
        if not options:
            return error_payload(tk, f"nenhuma opção encontrada para {u}.")

        refdate = res.get("refdate", "-")
        mat_str = res.get("maturity", active or "-")

        # OI enrichment (graceful — derivatives.db is optional here).
        pos_map: dict[str, dict] = {}
        op = _safe(_open_positions, underlying=u)
        if op.get("status") == "ok":
            for d in op.get("detail", []):
                t = (d.get("ticker") or "").upper()
                if t:
                    pos_map[t] = d

        def _rows(opts: list[dict]) -> list[list]:
            rows = []
            for o in opts:
                pos = pos_map.get((o.get("symbol") or "").upper())
                rows.append([
                    o.get("symbol", ""),
                    format_brl(o.get("strike_parsed")),
                    _fmt_date(o.get("maturity", "")),
                    format_brl(o.get("close")),
                    format_int(o.get("volume")),
                    format_brl(o.get("best_bid")),
                    format_brl(o.get("best_ask")),
                    format_int(pos.get("oi")) if pos else "-",
                    format_int(pos.get("covered")) if pos else "-",
                    format_int(pos.get("uncovered")) if pos else "-",
                ])
            return rows

        columns = ["Papel", "Exercício", "Vencimento", "Último", "Volume",
                   "Bid", "Ask", "OI", "Coberta", "Descoberta"]
        sections: list[dict[str, Any]] = []

        for label, key in (("Calls", "CALL"), ("Puts", "PUT")):
            side = [o for o in options if o.get("option_type") == key]
            if not side:
                continue
            # Cap: top-N by volume, note carries the real total.
            total = len(side)
            capped = sorted(
                side, key=lambda o: -(o.get("volume") or 0))[:_CHAIN_CAP]
            capped.sort(key=lambda o: float(o.get("strike_parsed") or 0))
            note = (f"Mostrando {len(capped)} de {total} — top por volume. "
                    "Clique nos cabeçalhos para reordenar."
                    if total > _CHAIN_CAP else "")
            sec = table_section(
                f"{label} — {u} ({self._fmt_mat(mat_str)})",
                columns, _rows(capped),
                description=(
                    f"{total} {label.lower()} para o vencimento {_fmt_date(mat_str)} "
                    f"(ref: {_fmt_date(refdate)}). Colunas OI/Coberta/Descoberta vêm "
                    "do derivatives.db (B3 API CSV bulk download) quando "
                    "disponível."
                ),
                note=note,
            )
            sec["sortable"] = True
            sec["pair_with_next"] = True  # Calls | Puts side by side
            sections.append(sec)

        # Ticker convention — reference material, demoted from the static
        # dashboard's first screen to the bottom of the tab.
        sections.append(table_section(
            "Convenção de Ticker de Opções",
            ["CALLS (compra)", "PUTS (venda)"],
            [["A=Jan  B=Fev  C=Mar  D=Abr", "M=Jan  N=Fev  O=Mar  P=Abr"],
             ["E=Mai  F=Jun  G=Jul  H=Ago", "Q=Mai  R=Jun  S=Jul  T=Ago"],
             ["I=Set  J=Out  K=Nov  L=Dez", "U=Set  V=Out  W=Nov  X=Dez"]],
            description=(
                "Formato: UNDERLYING + MÊS + STRIKE (PETRH36 = PETR call de "
                "agosto, strike R$ 36; dígito final 5 = meio-ponto, "
                "PETRA215 → R$ 21,50). A-L = calls; M-X = puts."
            ),
        ))

        return {"ticker": tk, "status": "ok", "sections": sections,
                "maturities": mats, "active_maturity": active}

    # ── 3/5: Volume & Exercícios ──────────────────────────────────────────

    def activity(self, ticker: str, maturity: str = "") -> dict[str, Any]:
        """What traded (volume by strike, per-maturity) + what got
        exercised (BDI 38/42, 90 pregões) — the two thin static tabs,
        merged and paired."""
        tk = (ticker or "").upper()
        u = _underlying(tk)
        sections: list[dict[str, Any]] = []

        mats, default_mat = self._maturity_pills(u)
        active = maturity if maturity in mats else default_mat

        any_ok = False

        # ── Volume por strike (maturity-scoped) ─────────────────────────
        vbs = _safe(volume_by_strike, underlying=u, maturity=active)
        if vbs.get("status") == "ok" and vbs.get("strikes"):
            any_ok = True
            strikes = vbs["strikes"]
            v_ref, v_mat = vbs.get("refdate", "-"), vbs.get("maturity", "-")
            labels = [format_brl(s.get("strike")) for s in strikes]
            sections.append(chart_section(
                f"Volume por Strike — {u} ({self._fmt_mat(v_mat)})",
                {
                    "type": "bar",
                    "data": {
                        "labels": labels,
                        "datasets": [
                            {"label": "Volume Calls", "data":
                             [s.get("call_volume", 0) for s in strikes],
                             "backgroundColor": _COLOR_CALL, "borderWidth": 0},
                            {"label": "Volume Puts", "data":
                             [s.get("put_volume", 0) for s in strikes],
                             "backgroundColor": _COLOR_PUT, "borderWidth": 0},
                        ],
                    },
                    "options": {"scales": {
                        "x": {"ticks": {"maxTicksLimit": 25}},
                        "y": {"beginAtZero": True, "title": {
                            "display": True, "text": "Volume financeiro (R$)"}},
                    }},
                },
                description=(
                    f"Volume financeiro (R$) por strike para o vencimento "
                    f"{_fmt_date(v_mat)} (ref: {_fmt_date(v_ref)}). Barras verdes = calls; "
                    "vermelhas = puts."
                ),
            ))
            sections[-1]["pair_with_next"] = True  # paired w/ exercise chart
            # One merged table (the static had two) — strike-level detail.
            sec = table_section(
                "Volume por Strike — Detalhe",
                ["Strike", "Vol. Calls (R$)", "# Calls",
                 "Vol. Puts (R$)", "# Puts"],
                [[format_brl(s.get("strike")),
                  format_int(s.get("call_volume")),
                  format_int(s.get("call_count")),
                  format_int(s.get("put_volume")),
                  format_int(s.get("put_count"))] for s in strikes],
                description="Volume financeiro + número de contratos por "
                            "strike (mesmo vencimento do gráfico).",
            )
            sec["sortable"] = True
            sections.append(sec)

        # ── Exercícios (90 pregões, maturity-independent) ──────────────
        ex = _safe(exercise_summary, underlying=u, days=90)
        if ex.get("status") == "ok" and ex.get("observations"):
            any_ok = True
            ex_obs = ex["observations"]
            sections.append(chart_section(
                f"Exercícios de Opções — {u}",
                {
                    "type": "bar",
                    "data": {
                        "labels": [o["ref_date"] for o in ex_obs],
                        "datasets": [
                            {"label": "Exercício Calls", "data":
                             [o.get("call_exercise_volume", 0) or 0
                              for o in ex_obs],
                             "backgroundColor": _COLOR_CALL, "borderWidth": 0},
                            {"label": "Exercício Puts", "data":
                             [o.get("put_exercise_volume", 0) or 0
                              for o in ex_obs],
                             "backgroundColor": _COLOR_PUT, "borderWidth": 0},
                        ],
                    },
                    "options": {"scales": {
                        "x": {"ticks": {"maxTicksLimit": 12}},
                        "y": {"beginAtZero": True, "title": {
                            "display": True,
                            "text": "Volume de exercício (R$)"}},
                    }},
                },
                description=(
                    "Volume de exercício de calls (verde) + puts (vermelho) "
                    "nos últimos 90 pregões. Exercício = o titular exerce o "
                    "direito de comprar (call) ou vender (put) o ativo pelo "
                    "strike."
                ),
            ))
            last15 = list(reversed(ex_obs))[:15]
            sec = table_section(
                "Últimos Exercícios",
                ["Data", "Ex. Calls (R$)", "Ex. Puts (R$)", "Total (R$)"],
                [[_fmt_date(o["ref_date"]),
                  format_int(o.get("call_exercise_volume", 0)),
                  format_int(o.get("put_exercise_volume", 0)),
                  format_int(o.get("total", 0))] for o in last15],
                description="Últimos 15 dias com exercício (mais recente "
                            "primeiro).",
            )
            sec["sortable"] = True
            sections.append(sec)

        if not any_ok:
            return error_payload(
                tk, "Sem dados de atividade — sincronize a fonte "
                    "b3_cotahist (derivativos).")

        return {"ticker": tk, "status": "ok", "sections": sections,
                "maturities": mats, "active_maturity": active}

    # ── 4/5: Volatilidade Implícita ───────────────────────────────────────

    def iv(self, ticker: str, maturity: str = "") -> dict[str, Any]:
        """Black-Scholes IV: smile per maturity + term-structure heatmap
        (capped to strikes near spot × the nearest 8 expiries — the static
        615×291 wall is unreadable)."""
        tk = (ticker or "").upper()
        u = _underlying(tk)

        try:
            spot, spot_ref = _fetch_spot_price(u)
        except Exception as e:  # noqa: BLE001
            _log_err("iv spot", e)
            spot, spot_ref = None, None
        if spot is None:
            return error_payload(
                tk, "Não foi possível obter o preço spot de "
                    f"{u} no cotahist — verifique se o ativo está "
                    "sincronizado.")
        try:
            r_cont = _fetch_selic_rate()
        except Exception as e:  # noqa: BLE001
            _log_err("iv selic", e)
            r_cont = None
        if r_cont is None:
            return error_payload(
                tk, "Não foi possível obter a taxa Selic (série 432 do "
                    "SGS). Rode o sync do bcb_sgs para popular o sgs.db.")

        mats, default_mat = self._maturity_pills(u)
        active = maturity if maturity in mats else default_mat

        chain_res = _safe(options_chain, underlying=u, maturity=active)
        if chain_res.get("status") != "ok" or not chain_res.get("options"):
            return error_payload(
                tk, "Sem cadeia de opções — sincronize a fonte b3_cotahist.")

        options = chain_res["options"]
        refdate = chain_res.get("refdate") or spot_ref or ""
        mat_str = chain_res.get("maturity", active or "-")

        enriched = []
        for o in options:
            try:
                iv = _compute_iv_for_option(o, spot, r_cont, refdate or "")
            except Exception as e:  # noqa: BLE001
                _log_err("iv compute", e)
                iv = None
            enriched.append({**o, "_iv": iv})

        calls = sorted((o for o in enriched
                        if o.get("option_type") == "CALL"
                        and o.get("_iv") is not None),
                       key=lambda o: float(o.get("strike_parsed") or 0))
        puts = sorted((o for o in enriched
                       if o.get("option_type") == "PUT"
                       and o.get("_iv") is not None),
                      key=lambda o: float(o.get("strike_parsed") or 0))

        sections: list[dict[str, Any]] = []

        # ── Smile chart ────────────────────────────────────────────────
        smile_labels = ([format_brl(o.get("strike_parsed")) for o in calls]
                        or [format_brl(o.get("strike_parsed")) for o in puts])
        smile = chart_section(
            f"IV Smile — {u} ({self._fmt_mat(mat_str)})",
            {
                "type": "line",
                "data": {
                    "labels": smile_labels,
                    "datasets": [
                        {"label": "IV Calls", "data":
                         [round(o["_iv"] * 100, 2) for o in calls],
                         "borderColor": _COLOR_CALL,
                         "backgroundColor": _COLOR_CALL,
                         "borderWidth": 1.5, "pointRadius": 3,
                         "tension": 0.3},
                        {"label": "IV Puts", "data":
                         [round(o["_iv"] * 100, 2) for o in puts],
                         "borderColor": _COLOR_PUT,
                         "backgroundColor": _COLOR_PUT,
                         "borderWidth": 1.5, "pointRadius": 3,
                         "tension": 0.3},
                    ],
                },
                "options": {"scales": {
                    "x": {"title": {"display": True, "text": "Strike"},
                          "ticks": {"maxTicksLimit": 20}},
                    "y": {"title": {"display": True,
                                    "text": "Volatilidade Implícita (%)"}},
                }},
            },
            description=(
                f"IV por strike para o vencimento {_fmt_date(mat_str)} (ref: {_fmt_date(refdate)}"
                f"{' — ' + _fmt_date(spot_ref) if spot_ref and spot_ref != refdate else ''}). "
                f"Spot = {format_brl(spot)}; Selic (cont.) = "
                f"{r_cont * 100:.4f}% a.a. O 'smile' típico mostra IV mais "
                "alta nos strikes extremos (OTM) e mais baixa no ATM — "
                "desvios indicam skew de mercado."
            ),
        )
        sections.append(smile)

        # ── IV table ───────────────────────────────────────────────────
        iv_rows = []
        for o in sorted(enriched,
                        key=lambda o: (o.get("option_type") or "",
                                       float(o.get("strike_parsed") or 0))):
            iv = o.get("_iv")
            iv_rows.append([
                o.get("symbol", ""),
                (o.get("option_type") or "").title(),
                format_brl(o.get("strike_parsed")),
                format_brl(o.get("close")),
                format_pct(iv) if iv is not None else "-",
            ])
        sec = table_section(
            f"Volatilidade Implícita — {u} ({self._fmt_mat(mat_str)})",
            ["Papel", "Tipo", "Strike", "Prêmio", "IV"],
            iv_rows,
            description=(
                "IV via Black-Scholes (Newton-Raphson + bisection fallback). "
                "Opções sem IV (T≤0, prêmio < intrínseco, ou falha de "
                "convergência) mostram '-'."
            ),
        )
        sec["sortable"] = True
        sec["pair_with_next"] = True  # pairs with the heatmap below
        sections.append(sec)

        # ── Term structure heatmap (capped) ────────────────────────────
        heat_mats = mats[:_HEAT_MATURITY_CAP] or ([mat_str]
                                                   if mat_str != "-" else [])
        if heat_mats:
            strike_set: set[float] = set()
            iv_map: dict[tuple[float, str], float | None] = {}
            for mat in heat_mats:
                if mat == mat_str and options:
                    opts_for_mat, mat_ref = options, refdate
                else:
                    r = _safe(options_chain, underlying=u, maturity=mat)
                    if r.get("status") != "ok":
                        continue
                    opts_for_mat = r.get("options", [])
                    mat_ref = r.get("refdate") or refdate or ""
                for o in opts_for_mat:
                    k = o.get("strike_parsed")
                    if k is None:
                        continue
                    try:
                        k = float(k)
                    except (TypeError, ValueError):
                        continue
                    # Keep only strikes near spot (±25%) — the far wings
                    # blow up the row count without adding signal.
                    if spot and abs(k - spot) / spot > _HEAT_STRIKE_WINDOW:
                        continue
                    strike_set.add(k)
                    try:
                        iv_map[(k, mat)] = _compute_iv_for_option(
                            o, spot, r_cont, mat_ref or "")
                    except Exception as e:  # noqa: BLE001
                        _log_err("iv heatmap", e)
                        iv_map[(k, mat)] = None

            if strike_set:
                heat_rows = []
                for k in sorted(strike_set):
                    row: list[Any] = [format_brl(k)]
                    for mat in heat_mats:
                        iv = iv_map.get((k, mat))
                        row.append({"text": "-", "bg": "", "color": ""}
                                   if iv is None else
                                   {"text": format_pct(iv),
                                    "bg": _iv_color(iv),
                                    "color": _iv_text_color(iv)})
                    heat_rows.append(row)
                from webui.adapters.contract import heatmap_section
                sections.append(heatmap_section(
                    f"Estrutura a Termo de IV — {u}",
                    ["Strike"] + [self._fmt_mat(m) for m in heat_mats],
                    heat_rows,
                    description=(
                        f"Mapa de calor strike × vencimento, strikes até "
                        f"±{int(_HEAT_STRIKE_WINDOW * 100)}% do spot "
                        f"({format_brl(spot)}), {len(strike_set)} strikes × "
                        f"{len(heat_mats)} vencimentos mais próximos. Cor = "
                        "IV (verde=calma <10% → amarela ~55% → vermelha="
                        "pânico >100%). Mostra a superfície de volatilidade "
                        "— o smile em cada vencimento + a estrutura a termo."
                    ),
                ))

        return {"ticker": tk, "status": "ok", "sections": sections,
                "maturities": mats, "active_maturity": active}

    # ── 5/5: Posições ─────────────────────────────────────────────────────

    def positions(self, ticker: str) -> dict[str, Any]:
        """Who's positioned where — OI walls + coverage + the per-option
        breakdown (CALL and PUT tables split, top 50 by OI each)."""
        tk = (ticker or "").upper()
        u = _underlying(tk)

        res = _safe(_open_positions, underlying=u)
        if res.get("status") != "ok":
            return error_payload(
                tk, "Sem dados de posições — sincronize a fonte "
                    "b3_derivatives (derivatives.db + instruments.db, "
                    "CSV bulk download da B3).")

        summary = res.get("summary", {}) or {}
        by_strike = res.get("by_strike", []) or []
        detail = res.get("detail", []) or []
        refdate = res.get("refdate", "-")

        call_sum = summary.get("CALL", {}) or {}
        put_sum = summary.get("PUT", {}) or {}
        total_oi = (call_sum.get("oi", 0) or 0) + (put_sum.get("oi", 0) or 0)
        call_oi = call_sum.get("oi", 0) or 0
        put_oi = put_sum.get("oi", 0) or 0
        cp_oi = (put_oi / call_oi) if call_oi > 0 else None
        ttl = (call_sum.get("total", 0) or 0) + (put_sum.get("total", 0) or 0)
        cov = (call_sum.get("covered", 0) or 0) + (put_sum.get("covered", 0) or 0)
        unc = (call_sum.get("uncovered", 0) or 0) + (put_sum.get("uncovered", 0) or 0)
        cov_pct = (cov / ttl * 100.0) if ttl > 0 else None
        unc_pct = (unc / ttl * 100.0) if ttl > 0 else None

        kpis = [
            kpi("OI Total", format_int(total_oi),
                f"Interesse aberto somado (calls + puts) em {_fmt_date(refdate)}."),
            kpi("Call/Put OI", format_value(cp_oi, "ratio")
                if cp_oi is not None else "-",
                "> 1 = mais posições em puts (bearish); < 1 = mais em "
                "calls (bullish)."),
            kpi("Cobertura", format_pct(cov_pct / 100.0)
                if cov_pct is not None else "-",
                "Posições cobertas (com lastro) / total."),
            kpi("Descobertura", format_pct(unc_pct / 100.0)
                if unc_pct is not None else "-",
                "Posições sem lastro (naked) / total."),
            kpi("Titulares", format_int(
                (call_sum.get("holders", 0) or 0)
                + (put_sum.get("holders", 0) or 0)),
                "Compradores da opção (holders/longs), calls + puts."),
            kpi("Lançadores", format_int(
                (call_sum.get("writers", 0) or 0)
                + (put_sum.get("writers", 0) or 0)),
                "Vendedores da opção (writers/shorts), calls + puts."),
        ]

        sections: list[dict[str, Any]] = []

        # OI walls chart.
        if by_strike:
            sections.append(chart_section(
                f"Interesse Aberto por Strike — {u}",
                {
                    "type": "bar",
                    "data": {
                        "labels": [format_brl(s.get("strike"))
                                   for s in by_strike],
                        "datasets": [
                            {"label": "OI Calls", "data":
                             [s.get("call_oi", 0) for s in by_strike],
                             "backgroundColor": _COLOR_CALL, "borderWidth": 0},
                            {"label": "OI Puts", "data":
                             [s.get("put_oi", 0) for s in by_strike],
                             "backgroundColor": _COLOR_PUT, "borderWidth": 0},
                        ],
                    },
                    "options": {"scales": {
                        "x": {"ticks": {"maxTicksLimit": 25}},
                        "y": {"beginAtZero": True, "title": {
                            "display": True,
                            "text": "Open Interest (contratos)"}},
                    }},
                },
                description=(
                    f"Open Interest por strike (ref: {_fmt_date(refdate)}). "
                    "Concentrações de OI indicam 'paredões' de suporte "
                    "(puts) ou resistência (calls) — níveis onde muitos "
                    "traders têm posições abertas e podem defender o preço."
                ),
            ))

        # Resumo CALL vs PUT.
        resumo_rows = [
            [ot,
             format_int((summary.get(ot) or {}).get("covered", 0)),
             format_int((summary.get(ot) or {}).get("blocked", 0)),
             format_int((summary.get(ot) or {}).get("uncovered", 0)),
             format_int((summary.get(ot) or {}).get("total", 0)),
             format_int((summary.get(ot) or {}).get("holders", 0)),
             format_int((summary.get(ot) or {}).get("writers", 0))]
            for ot in ("CALL", "PUT")
        ]
        sections.append(table_section(
            f"Resumo CALL vs PUT — {u}",
            ["Tipo", "Coberta", "Travada", "Descoberta", "Total",
             "Titulares", "Lançadores"],
            resumo_rows,
            description=(
                f"Comparação CALL vs PUT (ref: {_fmt_date(refdate)}). Coberta = lastro "
                "em ação; Travada = garantia em cash/bloqueada; Descoberta "
                "= sem lastro. Titulares = compradores; Lançadores = "
                "vendedores."
            ),
        ))

        # Per-option breakdown — CALL and PUT split, top-N by OI each.
        detail_columns = ["Ticker", "Tipo", "Strike", "Vencimento", "Dias",
                          "OI", "Var OI", "Coberta", "Descoberta",
                          "Titulares", "Lançadores"]

        def _detail_rows(rows: list[dict]) -> list[list]:
            out = []
            for d in rows:
                out.append([
                    d.get("ticker", ""),
                    (d.get("type") or "").title(),
                    format_brl(d.get("strike")),
                    _fmt_date(d.get("expiration") or "-"),
                    format_int(d.get("days_to_expiration")),
                    format_int(d.get("oi")),
                    format_int(d.get("var_oi")),
                    format_int(d.get("covered")),
                    format_int(d.get("uncovered")),
                    format_int(d.get("holders")),
                    format_int(d.get("writers")),
                ])
            return out

        for label, key in (("CALL", "CALL"), ("PUT", "PUT")):
            side = [d for d in detail
                    if (d.get("type") or "").upper() == key]
            if not side:
                continue
            total = len(side)
            capped = sorted(side, key=lambda d: -(d.get("oi") or 0)
                            if isinstance(d.get("oi"), (int, float))
                            else 0)[:_POS_CAP]
            capped.sort(key=lambda d: float(d.get("strike") or 0)
                        if isinstance(d.get("strike"), (int, float)) else 0)
            note = (f"Mostrando {len(capped)} de {total} — top por OI. "
                    "Clique nos cabeçalhos para reordenar."
                    if total > _POS_CAP else "")
            sec = table_section(
                f"Posições — {label} — {u}",
                detail_columns, _detail_rows(capped),
                description=(
                    f"{total} {label.lower()}s com posição aberta (ref: "
                    f"{_fmt_date(refdate)}). Join com instruments.db quando disponível "
                    "(strike + vencimento + estilo preenchidos). Var OI = "
                    "variação diária do interesse aberto."
                ),
                note=note,
            )
            sec["sortable"] = True
            sec["pair_with_next"] = True  # CALL | PUT side by side
            sections.append(sec)

        return {"ticker": tk, "status": "ok", "kpis": kpis,
                "sections": sections}
