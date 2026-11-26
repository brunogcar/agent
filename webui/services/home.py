"""webui/services/home.py — Painel (landing page) data service.

[v1.19] The landing page of the WebUI — a one-screen summary of the
Brazilian market. The old dashboard was a sync ribbon + three hardcoded
company suggestions; the sync details moved to the bottom box (and the
full panel stays on the Sincronização page), and the page itself now
answers "where does Brazil stand?" in one glance:

  KPI row    → Selic (anualizada) · TR · IPCA (mês) · IPCA (12m) ·
               IGP-M (mês) · IGP-M (12m) · USD/BRL (ptax)  [BCB SGS]
  ETF row    → BOVA11 · SMAL11 · IVVB11 — last close + day % [cotahist,
               v1.28.1: "add kpi to BOVA11 SMAL11 IVVB11 with the % it
               rose or fell"; v1.28.2 the row actually FILLS — the
               snapshot's universe now includes ETFs, BDI 14]
  7 cards    → Top 10 IBOV · Top 10 SMLL          [b3-index + cotahist]
               Mais Negócios · Maiores Volumes ·
               Maiores Altas · Maiores Baixas ·
               Maiores Altas BDR                  [cotahist]
               (v1.28.2: the BDR card sits AFTER Maiores Baixas — the
               native rankings first, the BDR slice last — and it FILLS
               now that BDR rows reach the DB, BDI 34/35/36)

[v1.21 fix 1] KPI row reorganized (rates → inflation mês+12m → FX) with
the three additions the user asked (IPCA mês, IGP-M mês, TR); new
"Maiores Volumes (R$)" card right after Mais Negócios — the financial
volume (quantidade × preço do pregão), the cotahist ``volume`` column.

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
    (market_type=10, share-like BDIs — no options, no rights, no
    fractional-market duplicates; v1.28.2: the snapshot universe spans
    equities/FIIs/ETFs/BDRs and each row carries its bdi_code — the
    four ranking cards slice it to EQUITIES (bdi 2) so their content
    is unchanged, the BDR card scopes by ticker, the ETF row reads the
    three tickers). Gainers/losers require >= 100 trades
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
    TR_DAILY,
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

from tools.report_ops.formats import fmt_brl, fmt_num

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.b3.index.helpers import format_pct as _fmt_weight  # "10,886%"
# [v1.28.2] the shared *34/35/36 predicate — BDRs are the FOREIGN
# companies' shares traded on B3 (BDI 34/35/36, ticker suffix mirrors it)
from skills.ddm.dividends.helpers import is_bdr as _is_bdr

_MIN_TRADES = 100    # liquidity gate for the gainers/losers ranking

# [v1.28.1] The Painel's ETF row — the three reference ETFs the user
# asked for ("add kpi to BOVA11 SMAL11 IVVB11 with the % it rose or
# fell"). (ticker, what it replicates) — the tooltip's text.
_ETF_ROW = (("BOVA11", "Ibovespa"),
            ("SMAL11", "Índice Small Cap"),
            ("IVVB11", "S&P 500"))

from webui.services.settings import settings_service


def _card_rows() -> int:
    """[v1.20] Rows per ranking card — the home.card_rows SETTING
    (default 10; clamped to the schema's 5-25 range)."""
    n = settings_service().get("home.card_rows", 10)
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 10
    return max(5, min(25, n))


def _cache_ttl() -> float:
    """[v1.20] The landing payload's memoization TTL — the
    home.cache_seconds SETTING (default 60s, clamped 5-600).
    [v1.19 fix 1] Nothing on the page changes between syncs, and the OLD
    behavior fired the heavy snapshot per request (three concurrent page
    loads + the 30s sync-box refresh kept the server churning). The lock
    makes concurrent callers coalesce into ONE computation (single-
    flight); the TTL bounds staleness after a sync."""
    s = settings_service().get("home.cache_seconds", 60)
    try:
        s = float(s)
    except (TypeError, ValueError):
        s = 60.0
    return max(5.0, min(600.0, s))

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
    """Painel landing page — KPI row + ETF row + 7 ranked ticker cards
    (FLAT, no ticker)."""

    # ── KPI row (BCB SGS — same computation as the Macro family) ────────────
    def _kpis(self) -> tuple[list[dict[str, Any]], str | None]:
        """(kpis, degradation-note-or-None). Values degrade to '-'.

        [v1.21 fix 1] Organized order — rates (Selic, TR), then inflation
        (IPCA mês → 12m, IGP-M mês → 12m), then FX — with the three new
        entries (IPCA mês, IGP-M mês, TR).
        """
        selic = _last(SELIC_DAILY)
        tr = _last(TR_DAILY)
        fx = _last(USD_BRL)
        ipca_m = _observations(IPCA_MENSAL, 60)
        igpm_m = _observations(IGPM_MENSAL, 60)
        ipca_last = ipca_m[-1] if ipca_m else None
        igpm_last = igpm_m[-1] if igpm_m else None
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
            kpi("TR",
                _pct(tr.get("value")),
                "Taxa Referencial diária — remunera poupança e alguns "
                "financiamentos. "
                f"Ref: {_fmt_date(tr.get('ref_date'))}."),
            kpi("IPCA (mês)",
                _pct(ipca_last.get("value") if ipca_last else None),
                "IPCA — variação do mês (a meta do Copom é 3% a.a.). "
                f"Ref: {_fmt_date(ipca_last.get('ref_date')) if ipca_last else '-'}."),
            kpi("IPCA (12m)",
                _pct(ipca_12m),
                "IPCA acumulado em 12 meses — a leitura do calendário de "
                "metas do Copom (a meta atual é 3%). "
                f"Ref: {_fmt_date(ipca_last.get('ref_date')) if ipca_last else '-'}."),
            kpi("IGP-M (mês)",
                _pct(igpm_last.get("value") if igpm_last else None),
                "IGP-M — variação do mês (preços ao produtor). "
                f"Ref: {_fmt_date(igpm_last.get('ref_date')) if igpm_last else '-'}."),
            kpi("IGP-M (12m)",
                _pct(igpm_12m),
                "IGP-M acumulado em 12 meses — o índice de preços ao "
                "produtor que indexa aluguéis e contratos. "
                f"Ref: {_fmt_date(igpm_last.get('ref_date')) if igpm_last else '-'}."),
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

    # ── [v1.28.1] ETF row (cotahist) ─────────────────────────────────────────
    @staticmethod
    def _etfs(quotes: dict | None) -> list[dict[str, Any]]:
        """BOVA11 / SMAL11 / IVVB11 — close + signed day % from the same
        snapshot the cards read. Empty when cotahist is down (the row
        renders nothing — the KPI note already names the source).

        [v1.28.2] The row actually FILLS now: ETFs carry BDI 14 in
        COTAHIST, and the snapshot's old ``bdi_code = 2`` scope excluded
        them — the row rendered empty on every real DB (the sandbox's
        synthetic cotahist.db was the only place it ever worked). The
        share-like universe fix lives in market_snapshot()."""
        out: list[dict[str, Any]] = []
        for tk, what in _ETF_ROW:
            q = (quotes or {}).get(tk) or {}
            if not q.get("close"):
                continue
            out.append({
                "ticker": tk,
                "value": _quote_text(q.get("close")),
                "variation": _signed_pct(q.get("variation_pct")),
                "tooltip": (f"ETF que replica o {what} — fechamento e "
                            "variação do último pregão com negócio "
                            "(COTAHIST)."),
            })
        return out

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

        constituents = data["constituents"][:_card_rows()]
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
        """Mais negócios + maiores volumes + altas + baixas (latest session).

        [v1.19 fix 1] Takes the ALREADY-FETCHED snapshot (see _quotes).
        [v1.21 fix 1] "Maiores Volumes (R$)" joins after Mais Negócios —
        ranked by the session's FINANCIAL volume (quantidade × preço, the
        cotahist ``volume`` column); the quote rides as the row's extra.
        """
        if snap.get("status") != "ok":
            err = {"subtitle": "", "error": _COTAHIST_ERR, "items": []}
            return [
                {"key": "negocios", "title": "Mais Negócios", **err},
                {"key": "volumes", "title": "Maiores Volumes (R$)", **err},
                {"key": "altas", "title": "Maiores Altas", **err},
                {"key": "baixas", "title": "Maiores Baixas", **err},
                {"key": "altas_bdr", "title": "Maiores Altas BDR", **err},
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

        # [v1.28.2] The four ranking cards stay NATIVES-ONLY (BDI 2) —
        # their content is byte-identical to what they always showed.
        # The snapshot's universe spans equities/FIIs/ETFs/BDRs now (it
        # has to: the ETF row and the BDR card read it), so the slice is
        # explicit instead of implicit in the SQL.
        natives = [s for s in symbols if s.get("bdi_code") == 2]

        # Mais negócios — by trade_count (volume as the card's context).
        top = _card_rows()
        by_trades = sorted(natives, key=lambda s: -s["trade_count"])[:top]
        trades_card = {
            "key": "negocios", "title": "Mais Negócios", "subtitle": sub,
            "error": None,
            "items": [row(s, {"label": "negócios",
                              "text": fmt_num(s["trade_count"], decimals=0)})
                      for s in by_trades],
        }

        # Maiores volumes — financial volume (quantidade × preço).
        by_volume = sorted(natives, key=lambda s: -s.get("volume") or 0.0)[:top]
        volume_card = {
            "key": "volumes", "title": "Maiores Volumes (R$)", "subtitle": sub,
            "error": None,
            "items": [{
                "ticker": s["ticker"],
                "name": s["name"],
                "value": fmt_brl(s.get("volume") or 0.0),
                "variation": _signed_pct(s.get("variation_pct")),
                "extra": {"label": "cotação",
                          "text": _quote_text(s.get("close"))},
            } for s in by_volume],
        }

        # Variações — close vs previous session, liquidity-gated.
        liquid = [s for s in natives
                  if s.get("variation_pct") is not None
                  and s["trade_count"] >= _MIN_TRADES]
        gainers = sorted(liquid, key=lambda s: -s["variation_pct"])[:top]
        losers = sorted(liquid, key=lambda s: s["variation_pct"])[:top]

        # [v1.28.1] Maiores Altas BDR — the same gainers ranking scoped
        # to the BDR universe (the Proventos family's is_bdr predicate:
        # BDRs are the FOREIGN companies' shares traded on B3), same
        # liquidity gate. [v1.28.2] the card MOVED after Maiores Baixas
        # (the user's ask: native rankings first, the BDR slice last) —
        # and the predicate itself is the SHARED helper (suffix 34/35/36,
        # no forked inline check — the no-forked-numerics rule,
        # predicates included). The BDR rows only exist in the DB after
        # the one-time cotahist re-sync (BDI 34/35/36 joined the sync
        # filter in v1.28.2).
        bdr_liquid = [s for s in symbols
                      if s.get("variation_pct") is not None
                      and s["trade_count"] >= _MIN_TRADES
                      and _is_bdr(s["ticker"])]
        bdr_gainers = sorted(bdr_liquid,
                             key=lambda s: -s["variation_pct"])[:top]

        return [
            trades_card,
            volume_card,
            {"key": "altas", "title": "Maiores Altas", "subtitle": sub,
             "error": None,
             "items": [row(s) for s in gainers]},
            {"key": "baixas", "title": "Maiores Baixas", "subtitle": sub,
             "error": None,
             "items": [row(s) for s in losers]},
            {"key": "altas_bdr", "title": "Maiores Altas BDR", "subtitle": sub,
             "error": None,
             "items": [row(s) for s in bdr_gainers]},
        ]

    # ── the landing payload ─────────────────────────────────────────────────
    def __init__(self) -> None:
        # [v1.19 fix 1] TTL memoization state — see _cache_ttl().
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._cached_at: float = 0.0
        # [v1.20] The settings the cached payload was built with — a
        # home.* change in Configurações busts the memo on the next call.
        self._cache_settings: tuple[int, float] | None = None

    def overview(self) -> dict[str, Any]:
        """One call, one screen: macro KPIs + 5 ranked ticker cards.

        [v1.19 fix 1] Memoized for home.cache_seconds (the v1.20 setting;
        60s default) under a lock (single-flight): concurrent loads
        coalesce into one computation and repeat loads are instant — the
        payload only changes on sync. [v1.20] A settings change (rows /
        TTL) invalidates the memo immediately.
        """
        with self._lock:
            current = (_card_rows(), _cache_ttl())
            if (self._cache is not None
                    and current == self._cache_settings
                    and time.monotonic() - self._cached_at < current[1]):
                return self._cache
            payload = self._compute()
            self._cache = payload
            self._cached_at = time.monotonic()
            self._cache_settings = current
            return payload

    def _compute(self) -> dict[str, Any]:
        kpis, kpis_note = self._kpis()
        snap = _market_snapshot()          # ONE call — quotes + rankings
        quotes = self._quotes(snap)
        etfs = self._etfs(quotes)
        cards = [
            self._index_card("IBOV", "IBOV · Top 10", quotes),
            self._index_card("SMLL", "SMLL · Top 10", quotes),
            *self._ranking_cards(snap),
        ]
        out: dict[str, Any] = {"status": "ok", "kpis": kpis,
                               "etfs": etfs, "cards": cards}
        if kpis_note:
            out["kpis_note"] = kpis_note
        return out
