"""webui/services/home.py — Painel (landing page) data service.

[v1.19] The landing page of the WebUI — a one-screen summary of the
Brazilian market. The old dashboard was a sync ribbon + three hardcoded
company suggestions; the sync details moved to the bottom box (and the
full panel stays on the Sincronização page), and the page itself now
answers "where does Brazil stand?" in one glance:

  KPI row        → [v1.28.3] MANAGED (home.kpis — the ⚙️ Gerenciar
                   Painel box organizes/hides/adds) in THREE separate
                   sets, per the user's review: (1) the macro KPI cards
                   (small boxes, as they always were — Selic, TR, IPCA
                   mês/12m, IGP-M mês/12m, USD/BRL by default) with the
                   NEW catalog options from the Mercado families
                   ("add more KPIs as options"): CDI (a.a.) + Meta
                   Selic [SGS], INPC mês/12m [ddm-inflation], Poupança
                   mês/12m [ddm-poupanca]; [v1.28.3] the families
                   COMPLETE — the Juros "mercado" twins (Selic/CDI/Meta
                   Selic mercado mês/12m [ddm-juros] — "slightly
                   different" from the SGS reads, exactly the user's
                   point) + the ANO acumulados (IPCA/IGP-M/INPC — ano
                   [ddm-inflation] + Poupança — ano [ddm-poupanca]);
                   (2) the ticker KPI cards (MEDIUM height — own grid,
                   ranking-card WIDTH, richer
                   than the v1.28.1 strips: price pill + day % + the
                   52-week position bar + Máx/Mín 52 sem + Volume do
                   dia); [v1.28.3] the card reads in THREE
                   HORIZONTAL BANDS (the header — ticker+badge+name
                   left, price pill + day % right · the FULL-WIDTH
                   green 52-week line chart with the value's dashed
                   reference line + the position bar under it · the
                   stats rows Mín 52 (first), Máx 52, Volume dia); (3) the ranking cards (full size,
                   as always) with the STANDARDIZED row —
                   "ticker - that extra info - price - %" (peso /
                   negócios / volume rides the info slot; the name fills
                   it for the altas/baixas cards; the volumes card's
                   cotação is now the main value with the pill).
  ticker cards   → [v1.28.3] the QUOTE CARDS, one per home.ticker_kpis
                   entry (default BOVA11/SMAL11/IVVB11) — ANY share-like
                   instrument now (ações, FIIs, ETFs, BDRs — "make it
                   support BDR and normal tickers as well"). Close +
                   signed day % + the 52-week range. The v1.28.1 ETF
                   row was three wide strips; [v1.28.3] these
                   live in their OWN grid between the macro KPIs and
                   the rankings ("i want them separately") — wider as
                   the rankings, in length between the old strips and
                   the ranking boxes, sized to carry the extra info.
  price scheme   → [v1.28.3] the MAIN PRICES on the Painel (the
                   ticker cards + every ranking row's price) render as
                   colored pills wearing the Ações family's 22-range
                   price palette (skills/_colors/price.py — "use color
                   scheme from mercado - Ações for the range of prices")
                   in the Insiders cargo/tipo pill display (rounded
                   chip, bold, the range label in the tooltip).
                   [v1.28.3] the scheme goes EVERYWHERE ("the
                   price color scheme, everywhere"): the SAME payload
                   (contract.price_pill — one shared builder) feeds the
                   Ações table's Última column (generic table cells),
                   the ⭐ Tickers Observados' Preço, the carteira
                   positions' Valor Hoje, the comparison's Última
                   Cotação row and the screener's peers table — always
                   on the MAIN price only ("if it has multiple prices
                   like min, max… just apply to main price": Máx/Mín
                   52s, PM, averages stay plain).
  ranking cards  → [v1.28.3] home.cards selects WHICH boxes show and in
                   what ORDER (the ⚙️ Gerenciar Painel box). Catalog:
                   Top 10 IBOV · Top 10 SMLL          [b3-index + cotahist]
                   Mais Negócios · Maiores Volumes ·
                   Maiores Altas · Maiores Baixas ·
                   Maiores Altas BDR · Maiores Quedas BDR [cotahist]
                   ("add box with maiores quedas BDR as well" — the
                   losers twin of v1.28.1's gainers card)

[v1.21 fix 1] KPI row reorganized (rates → inflation mês+12m → FX) with
the three additions the user asked (IPCA mês, IGP-M mês, TR); new
"Maiores Volumes (R$)" card right after Mais Negócios — the financial
volume (quantidade × preço do pregão), the cotahist ``volume`` column.

Every ticker row links to its company page (/webui/company/{ticker}).

Per the v1.7–v1.18 service lineage:
  - Data layer = the SAME query engines the skills' static dashboards run
    (read-only; no SQL duplication in the WebUI): BCB SGS (macro.py's
    helpers — no forked numerics), b3.index (Índices family's engine),
    the cotahist ``market_snapshot()`` (rankings + the quote map),
    [v1.28.3] ``quotes_for()`` + ``range_52w()`` (the ticker cards' own
    per-symbol fallback + the 52-week range) and [v1.28.3] the
    DDM family engines' ``last_value()`` (the KPI catalog's INPC +
    Poupança options) + ``skills/_colors/price.py`` (the price pill
    palette — the acoes.py precedent, no forked colors).
  - Degradation is SECTION-scoped: SGS down → KPIs show "-" + a note
    naming the ``sgs`` source; index.db down → the IBOV/SMLL cards carry
    the b3-index message (the Índices family's exact wording); cotahist
    down → the ranking cards name ``cotahist``; a ticker card whose
    symbol is absent everywhere degrades PER-CARD ("—" cells). The page
    NEVER blanks wholesale — each section degrades where its data lives.
  - Every number is a PRE-FORMATTED PT-BR string (comma decimals,
    explicit +/- signs on variations); the client only colorizes.
  - Variation = close vs the symbol's PREVIOUS COTAHIST SESSION
    (DENSE_RANK per symbol), lote padrão spot rows only
    (market_type=10, share-like BDIs — no options, no rights, no
    fractional-market duplicates; the snapshot universe spans
    equities/FIIs/ETFs/BDRs and each row carries its bdi_code — the
    four native ranking cards slice it to EQUITIES (bdi 2), the two
    BDR cards scope by ticker suffix, the ticker cards read their own
    symbols). Gainers/losers require >= 100 trades
    (illiquid one-lot prints would own the ranking).

Serving: ``GET /api/webui/home`` (api.py) → loadHomeData() in app.js
(KPI row via the shared valKpisHtml renderer; ticker cards + ranking
cards via the home-card renderers — links, not tables: the landing page
is a launcher).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from webui.adapters.contract import kpi
from webui.adapters.contract import price_pill as _pill

# ── the skill's data layer (single source of truth — same queries the
#    static dashboards run; no SQL duplication in the WebUI) ─────────────────
from data_sources.b3.index.query_engine import index as _query_index
from data_sources.b3.cotahist.query_engine import market_snapshot as _market_snapshot
# [v1.28.3] the ticker cards' per-symbol fallback (an illiquid paper
# silent for 10+ sessions falls out of the snapshot window — its LAST
# TRADED price is still the honest quote) + the 52-week range.
from data_sources.b3.cotahist.query_engine import quotes_for as _quotes_for
from data_sources.b3.cotahist.query_engine import range_52w as _range_52w
# [v1.28.3] The ticker cards' SPARKLINE — the trailing-52-week
# close series (≤40 points per symbol), the same window range_52w()
# aggregates ("1/3 of the space to a simple chart with line with green").
from data_sources.b3.cotahist.query_engine import series_52w as _series_52w

# ── macro.py's helpers (the no-forked-numerics rule: ONE definition of
#    Selic annualization, PT-BR percent/BRL formatting, 12m rolling sum) ─────
from webui.services.macro import (
    CDI_DAILY,
    IGPM_MENSAL,
    IPCA_MENSAL,
    META_COPOM,
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

# [v1.28.3] The Mercado families' engines — the KPI catalog's INPC
# (Inflação) and Poupança options ("add more KPIs as options from
# Mercado - Inflação, Juros, Poupança"). CDI and Meta Selic ride SGS
# (the same daily reads the Selic KPI makes — one source, one cache).
from data_sources.ddm.inflation.query_engine import last_value as _infl_last
from data_sources.ddm.poupanca.query_engine import last_value as _poup_last
# [v1.28.3] The JUROS family engine — the KPI catalog's "Selic
# mercado" options ("you didnt include some kpics with selic from
# mercado, they are slightly different"): the DDM monthly Selic reads
# differ slightly from the SGS daily annualization, and now both live
# in the catalog. The palette import below moved to the SHARED
# contract.price_pill() builder (one definition, every surface).
from data_sources.ddm.juros.query_engine import last_value as _juros_last

from tools.report_ops.formats import fmt_brl, fmt_num

# ── the skill's display helpers (no forked numerics) ────────────────────────
from skills.b3.index.helpers import format_pct as _fmt_weight  # "10,886%"
# [v1.28.2] the shared *34/35/36 predicate — BDRs are the FOREIGN
# companies' shares traded on B3 (BDI 34/35/36, ticker suffix mirrors it)
from skills.ddm.dividends.helpers import is_bdr as _is_bdr
# [v1.28.3] ONE ticker definition for every layer (webui/validators.py —
# the same RE the carteira CRUD uses; no forked predicates)
from webui.validators import TICKER_RE as _TICKER_RE

_MIN_TRADES = 100    # liquidity gate for the gainers/losers ranking

# [v1.28.3] The macro-KPI CATALOG — every KPI card the
# Painel can show, canonical order (taxas → inflação → poupança →
# câmbio). ``home.kpis`` (the ⚙️ Gerenciar Painel box) selects the subset
# AND the display order; unknown keys drop at read.
#
# [v1.28.3] THE MERCADO FAMILIES, COMPLETE ("you didnt include
# some kpics with selic from mercado… / IPCA — ano, IGP-M — ano, INPC
# — ano / Poupança — ano"): (a) the Juros family's own monthly reads
# join as the "mercado" twins of the SGS rates — Selic/CDI/Meta Selic
# mercado (mês/12m) [ddm-juros], slightly different numbers from the
# SGS annualizations (the DDM monthly series the Mercado → Juros page
# shows); (b) the ANO (year-to-date) acumulados the Inflação page
# carries — IPCA/IGP-M/INPC — ano [ddm-inflation, year_acumulado];
# (c) Poupança — ano [ddm-poupanca, acumulado_no_ano]. The default
# stays the v1.21 seven — everything new is an OPTION in the ⚙️ box.
_KPI_CATALOG: tuple[tuple[str, str], ...] = (
    ("selic_aa", "Selic (a.a.)"),
    ("selic_mercado_mes", "Selic mercado — mês"),
    ("selic_mercado_12m", "Selic mercado — 12m"),
    ("cdi_aa", "CDI (a.a.)"),
    ("cdi_mercado_mes", "CDI mercado — mês"),
    ("cdi_mercado_12m", "CDI mercado — 12m"),
    ("meta_selic", "Meta Selic"),
    ("meta_selic_mercado_mes", "Meta Selic mercado — mês"),
    ("meta_selic_mercado_12m", "Meta Selic mercado — 12m"),
    ("tr", "TR"),
    ("ipca_mes", "IPCA (mês)"),
    ("ipca_ano", "IPCA — ano"),
    ("ipca_12m", "IPCA (12m)"),
    ("igpm_mes", "IGP-M (mês)"),
    ("igpm_ano", "IGP-M — ano"),
    ("igpm_12m", "IGP-M (12m)"),
    ("inpc_mes", "INPC (mês)"),
    ("inpc_ano", "INPC — ano"),
    ("inpc_12m", "INPC (12m)"),
    ("poupanca_mes", "Poupança (mês)"),
    ("poupanca_ano", "Poupança — ano"),
    ("poupanca_12m", "Poupança (12m)"),
    ("usd_brl", "USD/BRL (ptax)"),
)
_KPI_TITLES: dict[str, str] = dict(_KPI_CATALOG)
# The v1.21 row — rates (Selic, TR), inflation mês → 12m, then FX — the
# default so the page opens exactly as it did before the catalog.
_KPI_DEFAULT: tuple[str, ...] = (
    "selic_aa", "tr", "ipca_mes", "ipca_12m", "igpm_mes", "igpm_12m",
    "usd_brl",
)

_BR_MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez")


def _ym_label(ym: Any) -> str:
    """'2026-10' → 'out/2026' (the DDM family tables' month label)."""
    s = str(ym or "")
    if (len(s) == 7 and s[4] == "-" and s[:4].isdigit()
            and s[5:].isdigit()):
        mi = int(s[5:]) - 1
        if 0 <= mi < 12:
            return f"{_BR_MONTHS[mi]}/{s[:4]}"
    return s or "-"

# [v1.28.3] The ranking-card CATALOG — every box the Painel can show, in
# canonical order. ``home.cards`` (the ⚙️ Gerenciar Painel box) selects the
# subset AND the display order; unknown keys are dropped at read. The
# catalog rides the payload (``card_catalog``) so the manage UI never
# hardcodes titles.
_CARD_CATALOG: tuple[tuple[str, str], ...] = (
    ("ibov", "IBOV · Top 10"),
    ("smll", "SMLL · Top 10"),
    ("negocios", "Mais Negócios"),
    ("volumes", "Maiores Volumes (R$)"),
    ("altas", "Maiores Altas"),
    ("baixas", "Maiores Baixas"),
    ("altas_bdr", "Maiores Altas BDR"),
    ("baixas_bdr", "Maiores Quedas BDR"),
)
_CARD_TITLES: dict[str, str] = dict(_CARD_CATALOG)

# [v1.28.3] The ticker cards' instrument badge — the snapshot's bdi_code
# names the kind (2=ação, 12=FII, 14=ETF, 34/35/36=BDR).
_KIND_BY_BDI = {2: "Ação", 12: "FII", 14: "ETF", 34: "BDR", 35: "BDR", 36: "BDR"}

from webui.services.settings import settings_service


def _ticker_kpis() -> list[str]:
    """[v1.28.3] home.ticker_kpis — the Painel's quote cards, in ORDER.

    The ⚙️ Gerenciar Painel box owns the list (arrange/add/remove); the
    settings page's comma input is the fallback editor. Any share-like
    instrument ("make it support BDR and normal tickers as well") — the
    B3 shape guard (validators.TICKER_RE) drops typos at read, dedupes,
    caps at 12 (a quote-card wall helps nobody).
    """
    raw = settings_service().get("home.ticker_kpis") or []
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        tk = str(t).strip().upper()
        if _TICKER_RE.match(tk) and tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out[:12]


def _kpis_setting() -> list[str]:
    """[v1.28.3] home.kpis — WHICH macro KPI cards show and in what
    ORDER (the enabled subset of the catalog, unknown keys dropped; the
    ⚙️ Gerenciar Painel box owns the list)."""
    raw = settings_service().get("home.kpis") or []
    return [k for k in raw if k in _KPI_TITLES]


def _cards_setting() -> list[str]:
    """[v1.28.3] home.cards — WHICH ranking boxes show and in what ORDER
    (the enabled subset of the catalog, unknown keys dropped)."""
    raw = settings_service().get("home.cards") or []
    return [k for k in raw if k in _CARD_TITLES]


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


def _price_pill(close: float | None) -> dict[str, str] | None:
    """[v1.28.3] The Ações price-range palette entry for a
    quote — now a thin delegate to the SHARED contract.price_pill()
    builder (the price scheme went EVERYWHERE this round: the same
    payload shape feeds the Ações table cells, the observados, the
    carteira positions, the comparison and the screener — one
    definition, no forked colors). None when there is no price to
    color (the client renders the plain text).
    """
    return _pill(close)


def _pos_52(close: float | None, high: float | None,
            low: float | None) -> int | None:
    """[v1.28.3] Where the close sits in the 52-week range,
    0–100 (the ticker card's position bar). None without a usable
    window (missing bounds, or a degenerate high ≤ low)."""
    if close is None or high is None or low is None:
        return None
    if high <= low or low <= 0:
        return None
    p = round((close - low) / (high - low) * 100)
    return max(0, min(100, int(p)))


# ── service ─────────────────────────────────────────────────────────────────
class HomeService:
    """Painel landing page — KPI row + ticker cards + the managed
    ranking-card set (FLAT, no ticker)."""

    # ── KPI row (BCB SGS + the DDM families — the home.kpis catalog) ────────
    def _kpis(self) -> tuple[list[dict[str, Any]], str | None]:
        """(kpis, degradation-note-or-None).

        [v1.28.3] home.kpis owns WHICH cards render and in WHAT
        ORDER (the ⚙️ Gerenciar Painel box); the seven v1.21 entries keep
        their exact labels and computations. The catalog's new options
        ride the same SGS reads where the series live (CDI, Meta Selic)
        and the DDM family engines otherwise (INPC, Poupança — read
        ONLY when one of their KPIs is enabled, so the default row
        never pays for a family DB it doesn't show).

        Per-KPI degradation (the house rule): a source that's down
        renders its card with "-" and a tooltip naming its sync
        source — the row never blanks wholesale, and a down SGS no
        longer hides the INPC/Poupança cards that don't depend on it.
        The kpis_note keeps its v1.19 role: the visible line under the
        row when the SGS block is fully down.
        """
        enabled = _kpis_setting()
        need = set(enabled)

        # ── SGS reads — one per series the ENABLED kpis need ──────────
        sgs: dict[str, dict[str, Any]] = {}
        for key, code in (("selic_aa", SELIC_DAILY), ("cdi_aa", CDI_DAILY),
                          ("meta_selic", META_COPOM), ("tr", TR_DAILY),
                          ("usd_brl", USD_BRL)):
            if key in need:
                sgs[key] = _last(code)
        monthly: dict[str, list[dict[str, Any]]] = {}
        for key, code in (("ipca", IPCA_MENSAL), ("igpm", IGPM_MENSAL)):
            if {key + "_mes", key + "_12m"} & need:
                monthly[key] = _observations(code, 60)

        note = None
        sgs_reads = list(sgs.values())
        if sgs_reads and all(_sgs_unavailable(r) for r in sgs_reads):
            note = _SGS_ERR

        def _sgs_val(key: str) -> Any:
            return sgs.get(key, {}).get("value")

        def _sgs_ref(key: str) -> Any:
            return _fmt_date(sgs.get(key, {}).get("ref_date"))

        def _mon(key: str) -> dict[str, Any]:
            obs = monthly.get(key) or []
            return obs[-1] if obs else {}

        def _mon_12m(key: str) -> Any:
            obs = monthly.get(key) or []
            return (_rolling_12m(obs)[-1].get("acum_12m")
                    if obs else None)

        # ── the DDM family reads — ONLY when their KPIs are enabled ───
        def _family(fetch) -> dict[str, Any]:
            try:
                return fetch()
            except Exception:
                return {"status": "error"}

        # [v1.28.3] The families grew per-SLUG: the Inflação
        # engine now serves ipca/igp-m/inpc (the ano KPIs read the SAME
        # last_value() the Inflação page shows), and the Juros family
        # joins with its three rates (the "mercado" Selic/CDI/Meta —
        # slightly different from the SGS reads, exactly why they're
        # separate options). LAZY per family: IPCA/IGP-M read
        # ddm-inflation ONLY for their — ano cards (the (mês)/(12m)
        # ones ride SGS); INPC and Poupança read their engines for
        # every window (no SGS twin here); the Juros rates only for
        # their mercado twins. The default seven never touch a DB.
        infl: dict[str, dict[str, Any]] = {}
        for slug_key, slug, keys in (
                ("inpc", "inpc", {"inpc_mes", "inpc_ano", "inpc_12m"}),
                ("ipca", "ipca", {"ipca_ano"}),
                ("igpm", "igp-m", {"igpm_ano"})):
            if keys & need:
                infl[slug_key] = _family(lambda s=slug: _infl_last(s))
        poup: dict[str, Any] | None = None
        if {"poupanca_mes", "poupanca_ano", "poupanca_12m"} & need:
            poup = _family(lambda: _poup_last("poupanca"))
        # The Juros "mercado" KPIs — slug per rate (ddm-juros).
        _JUROS_SLUGS = {"selic": "selic", "cdi": "cdi",
                        "meta_selic": "meta-selic"}
        juros: dict[str, dict[str, Any]] = {}
        for rate_key, slug in _JUROS_SLUGS.items():
            if {rate_key + "_mercado_mes",
                rate_key + "_mercado_12m"} & need:
                juros[rate_key] = _family(lambda s=slug: _juros_last(s))

        _INFL_ERR = ("Índice indisponível — sincronize a fonte "
                     "ddm-inflation (Inflação — DDM) na página "
                     "Sincronização.")
        _POUP_ERR = ("Poupança indisponível — sincronize a fonte "
                     "ddm-poupanca (Poupança — DDM) na página "
                     "Sincronização.")
        _JUROS_ERR = ("Taxa indisponível — sincronize a fonte "
                      "ddm-juros (DDM — juros) na página "
                      "Sincronização.")
        _SGS_DOWN_TIP = ("Série indisponível — sincronize a fonte sgs "
                         "(BCB — SGS) na página Sincronização.")

        kpis: list[dict[str, Any]] = []
        for k in enabled:
            if k == "selic_aa":
                v = _annualize(_sgs_val("selic_aa"))
                kpis.append(kpi("Selic (a.a.)", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("Taxa Selic diária anualizada (base 252) — a taxa "
                     "básica da economia. "
                     f"Ref: {_sgs_ref('selic_aa')}.") ))
            elif k == "cdi_aa":
                v = _annualize(_sgs_val("cdi_aa"))
                kpis.append(kpi("CDI (a.a.)", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("CDI diário anualizado (base 252) — a taxa do "
                     "interbank que remunera CDBs e fundos DI. "
                     f"Ref: {_sgs_ref('cdi_aa')}.") ))
            elif k == "meta_selic":
                v = _sgs_val("meta_selic")
                kpis.append(kpi("Meta Selic", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("Meta Selic definida pelo Copom — a taxa que orienta "
                     "a política monetária. "
                     f"Ref: {_sgs_ref('meta_selic')}.") ))
            elif k == "selic_mercado_mes":
                # [v1.28.3] The Juros family's Selic — the DDM
                # monthly read ("selic from mercado, they are slightly
                # different") vs the SGS daily annualization above.
                j = juros.get("selic") or {}
                ok = j.get("status") == "ok"
                v = j.get("month_value") if ok else None
                kpis.append(kpi("Selic mercado — mês", _pct(v),
                    _JUROS_ERR if not ok else
                    (f"Taxa Selic mensal do mercado (DDM — juros) — a "
                     f"leitura de {_ym_label(j.get('ref_date'))} que a "
                     "página Mercado → Juros mostra; a média no ano: "
                     f"{_pct(j.get('media_no_ano'))}.")))
            elif k == "selic_mercado_12m":
                j = juros.get("selic") or {}
                ok = j.get("status") == "ok"
                v = j.get("media_12m") if ok else None
                kpis.append(kpi("Selic mercado — 12m", _pct(v),
                    _JUROS_ERR if not ok else
                    ("Média das taxas Selic dos últimos 12 meses "
                     "(DDM — juros) — o nível de juros que suaviza os "
                     "movimentos do Copom.")))
            elif k == "cdi_mercado_mes":
                j = juros.get("cdi") or {}
                ok = j.get("status") == "ok"
                v = j.get("month_value") if ok else None
                kpis.append(kpi("CDI mercado — mês", _pct(v),
                    _JUROS_ERR if not ok else
                    (f"CDI mensal do mercado interbancário (DDM — juros) "
                     f"— leitura de {_ym_label(j.get('ref_date'))}; a "
                     f"média no ano: {_pct(j.get('media_no_ano'))}.")))
            elif k == "cdi_mercado_12m":
                j = juros.get("cdi") or {}
                ok = j.get("status") == "ok"
                v = j.get("media_12m") if ok else None
                kpis.append(kpi("CDI mercado — 12m", _pct(v),
                    _JUROS_ERR if not ok else
                    ("Média do CDI dos últimos 12 meses (DDM — juros).")))
            elif k == "meta_selic_mercado_mes":
                j = juros.get("meta_selic") or {}
                ok = j.get("status") == "ok"
                v = j.get("month_value") if ok else None
                kpis.append(kpi("Meta Selic mercado — mês", _pct(v),
                    _JUROS_ERR if not ok else
                    (f"Meta Selic mensal do Copom (DDM — juros) — leitura "
                     f"de {_ym_label(j.get('ref_date'))}; a média no ano: "
                     f"{_pct(j.get('media_no_ano'))}.")))
            elif k == "meta_selic_mercado_12m":
                j = juros.get("meta_selic") or {}
                ok = j.get("status") == "ok"
                v = j.get("media_12m") if ok else None
                kpis.append(kpi("Meta Selic mercado — 12m", _pct(v),
                    _JUROS_ERR if not ok else
                    ("Média da Meta Selic dos últimos 12 meses (DDM — "
                     "juros).")))
            elif k == "tr":
                v = _sgs_val("tr")
                kpis.append(kpi("TR", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("Taxa Referencial diária — remunera poupança e "
                     "alguns financiamentos. "
                     f"Ref: {_sgs_ref('tr')}.") ))
            elif k == "ipca_mes":
                last = _mon("ipca")
                v = last.get("value")
                kpis.append(kpi("IPCA (mês)", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("IPCA — variação do mês (a meta do Copom é 3% a.a.). "
                     f"Ref: {_fmt_date(last.get('ref_date'))}.") ))
            elif k == "ipca_ano":
                # [v1.28.3] The Inflação page's "IPCA — ano" — the
                # year-to-date acumulado from the SAME ddm-inflation
                # read that page shows (the SGS series the (mês)/(12m)
                # cards read carries no year acumulado).
                i = infl.get("ipca") or {}
                ok = i.get("status") == "ok"
                v = i.get("year_acumulado") if ok else None
                kpis.append(kpi("IPCA — ano", _pct(v),
                    _INFL_ERR if not ok else
                    (f"IPCA acumulado no ano — variação de jan a "
                     f"{_ym_label(i.get('ref_date'))} (IBGE — a mesma "
                     "leitura da página Mercado → Inflação).")))
            elif k == "ipca_12m":
                last = _mon("ipca")
                v = _mon_12m("ipca")
                kpis.append(kpi("IPCA (12m)", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("IPCA acumulado em 12 meses — a leitura do calendário "
                     "de metas do Copom (a meta atual é 3%). "
                     f"Ref: {_fmt_date(last.get('ref_date'))}.") ))
            elif k == "igpm_mes":
                last = _mon("igpm")
                v = last.get("value")
                kpis.append(kpi("IGP-M (mês)", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("IGP-M — variação do mês (preços ao produtor). "
                     f"Ref: {_fmt_date(last.get('ref_date'))}.") ))
            elif k == "igpm_ano":
                i = infl.get("igpm") or {}
                ok = i.get("status") == "ok"
                v = i.get("year_acumulado") if ok else None
                kpis.append(kpi("IGP-M — ano", _pct(v),
                    _INFL_ERR if not ok else
                    (f"IGP-M acumulado no ano — variação de jan a "
                     f"{_ym_label(i.get('ref_date'))} (FGV — o índice "
                     "que indexa aluguéis e contratos).")))
            elif k == "igpm_12m":
                last = _mon("igpm")
                v = _mon_12m("igpm")
                kpis.append(kpi("IGP-M (12m)", _pct(v),
                    _SGS_DOWN_TIP if v is None else
                    ("IGP-M acumulado em 12 meses — o índice de preços ao "
                     "produtor que indexa aluguéis e contratos. "
                     f"Ref: {_fmt_date(last.get('ref_date'))}.") ))
            elif k == "inpc_mes":
                i = infl.get("inpc") or {}
                ok = i.get("status") == "ok"
                v = i.get("month_value") if ok else None
                kpis.append(kpi("INPC (mês)", _pct(v),
                    _INFL_ERR if not ok else
                    (f"INPC — variação de {_ym_label(i.get('ref_date'))} "
                     "(IBGE — o IPCA é o índice amplo; o INPC cobre as "
                     "famílias com renda de até 5 salários mínimos). "
                     f"Acumulado no ano: "
                     f"{_pct(i.get('year_acumulado'))}.") ))
            elif k == "inpc_ano":
                i = infl.get("inpc") or {}
                ok = i.get("status") == "ok"
                v = i.get("year_acumulado") if ok else None
                kpis.append(kpi("INPC — ano", _pct(v),
                    _INFL_ERR if not ok else
                    (f"INPC acumulado no ano — variação de jan a "
                     f"{_ym_label(i.get('ref_date'))} (IBGE).")))
            elif k == "inpc_12m":
                i = infl.get("inpc") or {}
                ok = i.get("status") == "ok"
                v = i.get("acumulado_12m") if ok else None
                kpis.append(kpi("INPC (12m)", _pct(v),
                    _INFL_ERR if not ok else
                    ("INPC acumulado em 12 meses (janela móvel) — a "
                     "leitura que acompanha a remuneração de salários e "
                     "contratos. Fonte: IBGE (DDM Inflação).") ))
            elif k == "poupanca_mes":
                ok = poup is not None and poup.get("status") == "ok"
                v = poup.get("month_value") if ok else None
                kpis.append(kpi("Poupança (mês)", _pct(v),
                    _POUP_ERR if not ok else
                    (f"Rendimento da caderneta em "
                     f"{_ym_label(poup.get('ref_date'))} — 0,5% a.m. + TR "
                     "quando a Selic está acima de 8,5% a.a.; 70% da "
                     "Selic + TR abaixo. Acumulado no ano: "
                     f"{_pct(poup.get('acumulado_no_ano'))}.") ))
            elif k == "poupanca_ano":
                # [v1.28.3] "Poupança — ano" — the year-to-date
                # acumulado_no_ano from ddm-poupanca (the Poupança
                # page's own reading).
                ok = poup is not None and poup.get("status") == "ok"
                v = poup.get("acumulado_no_ano") if ok else None
                kpis.append(kpi("Poupança — ano", _pct(v),
                    _POUP_ERR if not ok else
                    (f"Rendimento da caderneta acumulado de jan a "
                     f"{_ym_label(poup.get('ref_date'))} — o que a "
                     "poupança pagou neste ano.")))
            elif k == "poupanca_12m":
                ok = poup is not None and poup.get("status") == "ok"
                v = poup.get("acumulado_12m") if ok else None
                kpis.append(kpi("Poupança (12m)", _pct(v),
                    _POUP_ERR if not ok else
                    ("Poupança acumulada em 12 meses — o que a caderneta "
                     "pagou (a comparação com IPCA e CDI está em Mercado "
                     "→ Poupança).") ))
            elif k == "usd_brl":
                v = _sgs_val("usd_brl")
                kpis.append(kpi("USD/BRL (ptax)", _brl4(v),
                    _SGS_DOWN_TIP if v is None else
                    ("Dólar venda — taxa ptax de fechamento. "
                     f"Ref: {_sgs_ref('usd_brl')}.") ))
        return kpis, note

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

    # ── [v1.28.3] ticker cards (home.ticker_kpis — any share-like) ──────────
    @staticmethod
    def _kind_label(bdi_code: int | None, ticker: str) -> str:
        """The instrument badge — the snapshot's bdi_code, the *34/35/36
        suffix as the fallback (a quotes_for row missed by the snapshot
        still carries bdi; a totally unknown paper reads "Ativo")."""
        if bdi_code in _KIND_BY_BDI:
            return _KIND_BY_BDI[bdi_code]
        return "BDR" if _is_bdr(ticker) else "Ativo"

    def _ticker_cards(self, quotes: dict | None) -> list[dict[str, Any]]:
        """One quote card per home.ticker_kpis entry — close + signed
        day % + the 52-week range + the day volume, ANY share-like
        instrument (ações, FIIs, ETFs, BDRs).

        [v1.28.3] The card gained the extras the MEDIUM size buys
        ("in length a bit bigger to display more info"): the price pill
        (the Ações 22-range palette) and the 52-week POSITION bar
        (pos_52 — where the close sits between low and high, painted
        with the same band color) over the Volume (dia) row.

        Quotes come from the SAME snapshot the cards read; a symbol the
        snapshot window missed (illiquid, silent 10+ sessions) falls
        back to quotes_for() — its own last session, the honest "last
        traded" price. A symbol absent everywhere still renders — a
        degraded card with "—" cells (per-card degradation, the house
        rule). The 52-week range rides ONE range_52w() call for the
        whole list.
        """
        tickers = _ticker_kpis()
        if not tickers:
            return []

        qmap: dict[str, dict[str, Any]] = dict(quotes or {})
        missing = [t for t in tickers if t not in qmap]
        if missing:
            res = _quotes_for(missing)
            if res.get("status") == "ok":
                for s in res.get("symbols", []):
                    qmap[s["ticker"]] = s

        r52: dict[str, dict[str, Any]] = {}
        res = _range_52w(tickers)
        if res.get("status") == "ok":
            r52 = {r["ticker"]: r for r in res.get("symbols", [])}

        # [v1.28.3] The SPARKLINE series — the same 52-week window
        # as r52, as the close series (≤40 points). ONE call for the
        # whole list; a symbol absent from the window degrades to a
        # spark-less card (the chart band renders the empty state).
        spark: dict[str, list[float]] = {}
        res = _series_52w(tickers)
        if res.get("status") == "ok":
            spark = {s["ticker"]: s["points"]
                     for s in res.get("symbols", []) if s.get("points")}

        out: list[dict[str, Any]] = []
        for tk in tickers:
            q = qmap.get(tk) or {}
            rng = r52.get(tk) or {}
            kind = self._kind_label(q.get("bdi_code"), tk)
            name = (q.get("name") or "").strip()
            close = q.get("close")
            high = rng.get("high_52")
            low = rng.get("low_52")
            out.append({
                "ticker": tk,
                "name": name,
                "kind": kind,
                "value": _quote_text(close),
                "price": _price_pill(close),
                "variation": _signed_pct(q.get("variation_pct")),
                "high_52": _brl2(high) if high is not None else None,
                "low_52": _brl2(low) if low is not None else None,
                "pos_52": _pos_52(close, high, low),
                # [v1.28.3] the 52-week close series — the chart
                # band's green line, last point = the quoted price (the
                # dashed reference line marks it in the band color).
                "spark": spark.get(tk),
                "volume": (fmt_brl(q.get("volume"))
                           if q.get("volume") else None),
                "tooltip": (f"{name or tk} · {kind} — cotação e variação do "
                            "último pregão com negócio (COTAHIST); máx/mín "
                            "das últimas 52 semanas; volume financeiro do "
                            "pregão."),
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
                "price": _price_pill(
                    quotes.get(c["ticker"], {}).get("close")
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
        """Mais negócios + maiores volumes + altas + baixas + the two BDR
        slices (latest session).

        [v1.19 fix 1] Takes the ALREADY-FETCHED snapshot (see _quotes).
        [v1.21 fix 1] "Maiores Volumes (R$)" joins after Mais Negócios —
        ranked by the session's FINANCIAL volume (quantidade × preço, the
        cotahist ``volume`` column); the quote rides as the row's extra.
        [v1.28.3] "Maiores Quedas BDR" — the losers twin of v1.28.1's
        gainers card ("add box with maiores quedas BDR as well"), same
        universe, same liquidity gate, right after Maiores Altas BDR.
        """
        if snap.get("status") != "ok":
            err = {"subtitle": "", "error": _COTAHIST_ERR, "items": []}
            return [
                {"key": "negocios", "title": "Mais Negócios", **err},
                {"key": "volumes", "title": "Maiores Volumes (R$)", **err},
                {"key": "altas", "title": "Maiores Altas", **err},
                {"key": "baixas", "title": "Maiores Baixas", **err},
                {"key": "altas_bdr", "title": "Maiores Altas BDR", **err},
                {"key": "baixas_bdr", "title": "Maiores Quedas BDR", **err},
            ]

        session = _fmt_date(snap.get("session_date", "")) or "-"
        symbols = snap.get("symbols", [])
        sub = f"Pregão de {session}"

        def row(s: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
            # [v1.28.3] The STANDARDIZED ranking row —
            # "ticker - that extra info - price - %": the extra (peso,
            # negócios, volume…) rides right after the ticker and the
            # PRICE is always the row's main value (pill). The NAME
            # moves to the tooltip when an extra exists (the client
            # shows it in the info slot otherwise).
            return {
                "ticker": s["ticker"],
                "name": s["name"],
                "value": _quote_text(s.get("close")),
                "price": _price_pill(s.get("close")),
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
        # [v1.28.3] The row STANDARDIZED with every other card:
        # "ticker - that extra info - price - %" — the VOLUME rides the
        # info slot (label "volume") and the COTAÇÃO is the row's main
        # value, wearing the price-band pill like every ranking price
        # (the old shape had the volume as the main value and the price
        # as the extra — the user's ask unifies the row grammar).
        by_volume = sorted(natives, key=lambda s: -s.get("volume") or 0.0)[:top]
        volume_card = {
            "key": "volumes", "title": "Maiores Volumes (R$)", "subtitle": sub,
            "error": None,
            "items": [row(s, {"label": "volume",
                              "text": fmt_brl(s.get("volume") or 0.0)})
                      for s in by_volume],
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
        # filter in v1.28.2). [v1.28.3] Maiores Quedas BDR joins right
        # after it — the losers twin (ascending variation, same gate).
        bdr_liquid = [s for s in symbols
                      if s.get("variation_pct") is not None
                      and s["trade_count"] >= _MIN_TRADES
                      and _is_bdr(s["ticker"])]
        bdr_gainers = sorted(bdr_liquid,
                             key=lambda s: -s["variation_pct"])[:top]
        bdr_losers = sorted(bdr_liquid,
                            key=lambda s: s["variation_pct"])[:top]

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
            {"key": "baixas_bdr", "title": "Maiores Quedas BDR", "subtitle": sub,
             "error": None,
             "items": [row(s) for s in bdr_losers]},
        ]

    # ── the landing payload ─────────────────────────────────────────────────
    def __init__(self) -> None:
        # [v1.19 fix 1] TTL memoization state — see _cache_ttl().
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._cached_at: float = 0.0
        # [v1.20] The settings the cached payload was built with — a
        # home.* change in Configurações busts the memo on the next call.
        # [v1.28.3] ticker_kpis + cards joined the key (the ⚙️ Gerenciar
        # Painel box saves them — the Painel must reflect a save
        # immediately, not after the TTL).
        self._cache_settings: tuple[Any, ...] | None = None

    def overview(self) -> dict[str, Any]:
        """One call, one screen: macro KPIs + ticker cards + the managed
        ranking-card set.

        [v1.19 fix 1] Memoized for home.cache_seconds (the v1.20 setting;
        60s default) under a lock (single-flight): concurrent loads
        coalesce into one computation and repeat loads are instant — the
        payload only changes on sync. [v1.20] A settings change (rows /
        TTL) invalidates the memo immediately. [v1.28.3] …and so does
        any ticker_kpis/cards change (the Gerenciar box's saves).
        """
        with self._lock:
            current = (_card_rows(), _cache_ttl(),
                       tuple(_ticker_kpis()), tuple(_cards_setting()),
                       tuple(_kpis_setting()))
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
        ticker_cards = self._ticker_cards(quotes)

        # [v1.28.3] home.cards owns WHICH ranking boxes render and in
        # what ORDER (the ⚙️ Gerenciar Painel box; unknown keys dropped
        # at read). The two b3-index cards build on demand; the six
        # cotahist cards come from the one _ranking_cards() pass — both
        # wrapped as zero-arg callables so the loop below is uniform.
        rank = {c["key"]: (lambda c=c: c)
                for c in self._ranking_cards(snap)}
        builders: dict[str, Any] = {
            "ibov": lambda: self._index_card("IBOV", "IBOV · Top 10", quotes),
            "smll": lambda: self._index_card("SMLL", "SMLL · Top 10", quotes),
            **rank,
        }
        cards = [builders[k]() for k in _cards_setting() if k in builders]

        out: dict[str, Any] = {"status": "ok", "kpis": kpis,
                               "kpi_catalog": [{"key": k, "title": t}
                                                for k, t in _KPI_CATALOG],
                               "ticker_cards": ticker_cards,
                               "cards": cards,
                               "card_catalog": [{"key": k, "title": t}
                                                for k, t in _CARD_CATALOG]}
        if kpis_note:
            out["kpis_note"] = kpis_note
        return out
