"""webui/services/home.py — Painel (landing page) data service.

[v1.19] The landing page of the WebUI — a one-screen summary of the
Brazilian market. The old dashboard was a sync ribbon + three hardcoded
company suggestions; the sync details moved to the bottom box (and the
full panel stays on the Sincronização page), and the page itself now
answers "where does Brazil stand?" in one glance:

  KPI row    → Selic (anualizada) · IPCA (acumulado 12m) · IGP-M
               (acumulado 12m) · USD/BRL (ptax)  [BCB SGS]
  5 cards    → Top 10 IBOV · Top 10 SMLL          [b3-index + cotahist]
               Mais Negócios · Maiores Altas ·
               Maiores Baixas                     [cotahist]

Every ticker row links to its company page (/webui/company/{ticker}).

Per the v1.7–v1.18 service lineage:
  - Data layer = the SAME query engines the skills' static dashboards run
    (read-only; no SQL duplication in the WebUI): BCB SGS (macro.py's
    helpers — no forked numerics), b3.index (Índices family's engine) and
    the NEW cotahist ``market_snapshot()`` (data layer owns SQL).
  - Degradation is SECTION-scoped: SGS down → KPIs show "-" + a note
    naming the ``sgs`` source; index.db down → the IBOV/SMLL cards carry
    the b3-index message (the Índices family's exact wording); cotahist
    down → the three ranking cards name ``cotahist``. The page NEVER
    blanks wholesale — each section degrades exactly where its data lives.
  - Every number is a PRE-FORMATTED PT-BR string (comma decimals,
    explicit +/- signs on variations); the client only colorizes.
  - Variation = close vs the symbol's PREVIOUS COTAHIST SESSION
    (DENSE_RANK per symbol), lote padrão spot rows only
    (market_type=10, bdi_code=2 — no options, no rights, no
    fractional-market duplicates). Gainers/losers require >= 100 trades
    (illiquid one-lot prints would own the ranking).

Serving: ``GET /api/webui/home`` (api.py) → loadHomeData() in app.js
(KPI row via the shared valKpisHtml renderer; cards via the dedicated
home-card renderer — links, not tables: the landing page is a launcher).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from webui.adapters.contract import kpi

# ── the skill's data layer (single source of truth — same queries the
#    static dashboards run; no SQL duplication in the WebUI) ─────────────────
from data_sources.b3.index.query_engine import index as _query_index
from data_sources.b3.cotahist.query_engine import market_snapshot as _market_snapshot

# ── macro.py's helpers (the no-forked-numerics rule: ONE definition of
#    Selic annualization, PT-BR percent/BRL formatting, 12m rolling sum) ─────
from webui.services.macro import (
    IGPM_MENSAL,
    IPCA_MENSAL,
    SELIC_DAILY,
    USD_BRL,
    _annualize,
    _brl2,
    _brl4,
    _fmt_date,
    _last,
    _observations,
    _pct,
    _rolling_12m,
    _sgs_unavailable,
)

from tools.report_ops.formats import fmt_num

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.b3.index.helpers import format_pct as _fmt_weight  # "10,886%"

_TOP = 10            # rows per card (user request: "top 10")
_MIN_TRADES = 100    # liquidity gate for the gainers/losers ranking

# [v1.19 fix 1] The landing payload is memoized for this many seconds.
# Nothing on the page changes between syncs, and the OLD behavior fired
# the heavy snapshot per request (three concurrent page loads + the 30s
# sync-box refresh kept the server churning). The lock makes concurrent
# callers coalesce into ONE computation (single-flight); the TTL bounds
# staleness after a sync.
_CACHE_TTL = 60.0

_SGS_ERR = ("Dados macroeconômicos indisponíveis — sincronize a fonte "
            "sgs (BCB — Sistema Gerenciador de Séries Temporais) na "
            "página Sincronização.")
_COTAHIST_ERR = ("Cotações do pregão indisponíveis — sincronize a fonte "
                 "cotahist (B3 — COTAHIST) na página Sincronização.")
# Same wording as the Índices family (indexes.py) — one message per source.
_INDEX_ERR = ("Composição de índices indisponível — sincronize a fonte "
              "b3-index (Índices B3) na página Sincronização.")


# ── formatting ───────────────────────────────────────────────────────────────
def _signed_pct(v: float | None) -> str | None:
    """11.31 → '+11,31%'; -0.45 → '-0,45%'; None → None (client shows '—')."""
    if v is None:
        return None
    body = fmt_num(abs(v), decimals=2)
    sign = "+" if v > 0 else ("-" if v < 0 else "")
    return f"{sign}{body}%"


def _quote_text(close: float | None) -> str:
    """Close → 'R$ 34,50' ('—' without a synced quote)."""
    return _brl2(close) if close is not None else "—"


# ── service ─────────────────────────────────────────────────────────────────
class HomeService:
    """Painel landing page — KPI row + 5 ranked ticker cards (FLAT, no ticker)."""

    # ── KPI row (BCB SGS — same computation as the Macro family) ────────────
    def _kpis(self) -> tuple[list[dict[str, Any]], str | None]:
        """(kpis, degradation-note-or-None). Values degrade to '-'."""
        selic = _last(SELIC_DAILY)
        fx = _last(USD_BRL)
        ipca_m = _observations(IPCA_MENSAL, 60)
        igpm_m = _observations(IGPM_MENSAL, 60)
        ipca_12m = _rolling_12m(ipca_m)[-1].get("acum_12m") if ipca_m else None
        igpm_12m = _rolling_12m(igpm_m)[-1].get("acum_12m") if igpm_m else None

        if _sgs_unavailable(selic) and _sgs_unavailable(fx):
            return [], _SGS_ERR

        kpis = [
            kpi("Selic (a.a.)",
                _pct(_annualize(selic.get("value"))),
                "Taxa Selic diária anualizada (base 252) — a taxa básica da "
                "economia. "
                f"Ref: {_fmt_date(selic.get('ref_date'))}."),
            kpi("IPCA (12m)",
                _pct(ipca_12m),
                "IPCA acumulado em 12 meses — a leitura do calendário de "
                "metas do Copom (a meta atual é 3%). "
                f"Ref: {_fmt_date(ipca_m[-1].get('ref_date')) if ipca_m else '-'}."),
            kpi("IGP-M (12m)",
                _pct(igpm_12m),
                "IGP-M acumulado em 12 meses — o índice de preços ao "
                "produtor que indexa aluguéis e contratos. "
                f"Ref: {_fmt_date(igpm_m[-1].get('ref_date')) if igpm_m else '-'}."),
            kpi("USD/BRL (ptax)",
                _brl4(fx.get("value")),
                "Dólar venda — taxa ptax de fechamento. "
                f"Ref: {_fmt_date(fx.get('ref_date'))}."),
        ]
        return kpis, None

    # ── shared quote map (cotahist) ─────────────────────────────────────────
    @staticmethod
    def _quotes(snap: dict | None) -> dict[str, dict[str, Any]] | None:
        """ticker → latest quote row; None when cotahist is unavailable.

        [v1.19 fix 1] Takes the ALREADY-FETCHED snapshot — overview() used
        to call market_snapshot() twice (once here, once in
        _ranking_cards), doubling the heavy query per request.
        """
        if not snap or snap.get("status") != "ok":
            return None
        return {s["ticker"]: s for s in snap.get("symbols", [])}

    # ── index cards (IBOV / SMLL) ───────────────────────────────────────────
    def _index_card(self, code: str, title: str, quotes: dict | None
                    ) -> dict[str, Any]:
        """Top 10 constituents by weight, enriched with value + variation."""
        card: dict[str, Any] = {"key": code.lower(), "title": title,
                                "subtitle": "", "error": None, "items": []}
        try:
            data = _query_index(code)
        except Exception:
            data = {"status": "error"}
        if data.get("status") != "ok" or not data.get("constituents"):
            card["error"] = _INDEX_ERR
            return card

        constituents = data["constituents"][:_TOP]
        ref = _fmt_date(data.get("ref_date", ""))
        card["subtitle"] = f"Maiores pesos — carteira de {ref or '-'}"
        card["items"] = [
            {
                "ticker": c["ticker"],
                "name": c.get("company_name") or "",
                "value": _quote_text(quotes.get(c["ticker"], {}).get("close")
                                     if quotes else None),
                "variation": _signed_pct(
                    quotes.get(c["ticker"], {}).get("variation_pct")
                    if quotes else None),
                "extra": {"label": "peso",
                          "text": _fmt_weight(c.get("participation"))},
            }
            for c in constituents
        ]
        return card

    # ── cotahist ranking cards ──────────────────────────────────────────────
    def _ranking_cards(self, snap: dict) -> list[dict[str, Any]]:
        """Mais negócios + maiores altas + maiores baixas (latest session).

        [v1.19 fix 1] Takes the ALREADY-FETCHED snapshot (see _quotes).
        """
        if snap.get("status") != "ok":
            err = {"subtitle": "", "error": _COTAHIST_ERR, "items": []}
            return [
                {"key": "negocios", "title": "Mais Negócios", **err},
                {"key": "altas", "title": "Maiores Altas", **err},
                {"key": "baixas", "title": "Maiores Baixas", **err},
            ]

        session = _fmt_date(snap.get("session_date", "")) or "-"
        symbols = snap.get("symbols", [])
        sub = f"Pregão de {session}"

        def row(s: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
            return {
                "ticker": s["ticker"],
                "name": s["name"],
                "value": _quote_text(s.get("close")),
                "variation": _signed_pct(s.get("variation_pct")),
                "extra": extra,
            }

        # Mais negócios — by trade_count (volume as the card's context).
        by_trades = sorted(symbols, key=lambda s: -s["trade_count"])[:_TOP]
        trades_card = {
            "key": "negocios", "title": "Mais Negócios", "subtitle": sub,
            "error": None,
            "items": [row(s, {"label": "negócios",
                              "text": fmt_num(s["trade_count"], decimals=0)})
                      for s in by_trades],
        }

        # Variações — close vs previous session, liquidity-gated.
        liquid = [s for s in symbols
                  if s.get("variation_pct") is not None
                  and s["trade_count"] >= _MIN_TRADES]
        gainers = sorted(liquid, key=lambda s: -s["variation_pct"])[:_TOP]
        losers = sorted(liquid, key=lambda s: s["variation_pct"])[:_TOP]

        return [
            trades_card,
            {"key": "altas", "title": "Maiores Altas", "subtitle": sub,
             "error": None,
             "items": [row(s) for s in gainers]},
            {"key": "baixas", "title": "Maiores Baixas", "subtitle": sub,
             "error": None,
             "items": [row(s) for s in losers]},
        ]

    # ── the landing payload ─────────────────────────────────────────────────
    def __init__(self) -> None:
        # [v1.19 fix 1] TTL memoization state — see _CACHE_TTL.
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._cached_at: float = 0.0

    def overview(self) -> dict[str, Any]:
        """One call, one screen: macro KPIs + 5 ranked ticker cards.

        [v1.19 fix 1] Memoized for _CACHE_TTL seconds under a lock
        (single-flight): concurrent loads coalesce into one computation
        and repeat loads are instant — the payload only changes on sync.
        """
        with self._lock:
            if (self._cache is not None
                    and time.monotonic() - self._cached_at < _CACHE_TTL):
                return self._cache
            payload = self._compute()
            self._cache = payload
            self._cached_at = time.monotonic()
            return payload

    def _compute(self) -> dict[str, Any]:
        kpis, kpis_note = self._kpis()
        snap = _market_snapshot()          # ONE call — quotes + rankings
        quotes = self._quotes(snap)
        cards = [
            self._index_card("IBOV", "IBOV · Top 10", quotes),
            self._index_card("SMLL", "SMLL · Top 10", quotes),
            *self._ranking_cards(snap),
        ]
        out: dict[str, Any] = {"status": "ok", "kpis": kpis, "cards": cards}
        if kpis_note:
            out["kpis_note"] = kpis_note
        return out
