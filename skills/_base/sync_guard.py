"""skills/_base/sync_guard.py — Force-sync guard (v1.14).

When a user calls a skill, check if the required data sources are stale
(>24h since last sync). If stale, force-sync them BEFORE running the skill.

This is NOT auto-sync (scheduled cron). It's on-demand when a skill is used.
The first call of the day may take 30+ seconds (DFP sync); subsequent calls
within 24h are fast.

DESIGN (per LLM review consensus):
  - 24h freshness window for ALL sources (earnings season releases daily)
  - HEAD check before downloading (CVM only — compare Last-Modified header
    to last sync timestamp). Timeout=5s. On network error → sync anyway
    (safer to sync than to skip).
  - Current-year-only force sync (not full history) for DFP/ITR/FRE/etc.
  - bridge: sync only the requested ticker, not all tickers
  - Failure path: proceed with stale data + warning (don't hard-fail)
  - Escape hatches: CVM_SKIP_SYNC=1 env var + skip_sync=True kwarg
  - Re-entrancy: ContextVar guard (in route.py) ensures ensure_fresh()
    runs at most once per top-level route() call (dashboard composes
    other modes)

Provides:
  - SYNC_FRESHNESS_HOURS (constant)
  - _BRIDGE_SYNCED_TICKERS, _bridge_lock (session-level bridge dedup)
  - _HEAD_CACHE, _HEAD_TTL (HEAD-check result cache, 1h TTL)
  - _SYNC_REGISTRY + register_sync_source() — module-level source→sync-fn map
    (Phase 4 C3: extracted from the in-function sync_map literal so the
    dispatch table is built once at import time + can be extended by
    external callers via register_sync_source()).
  - _source_last_sync(source) — ISO timestamp string
  - _parse_sync_ts(ts) — datetime parser
  - _source_is_stale(source, max_age_hours) — bool
  - _cvm_has_new_data(source, year) — HEAD check
  - _cvm_has_new_data_cached(source, year) — TTL-cached HEAD check
  - _trigger_sync(source, company, trace_id) — _SYNC_REGISTRY dispatch
  - ensure_fresh(sources, company, skip_sync, trace_id) — main entry

Part of the skills/_base/ package split (was originally in skills/_base.py).
"""
from __future__ import annotations

import importlib
import os
import threading
from datetime import datetime, timedelta
from typing import Callable


# [Tier 0 #3] Session-level bridge sync dedup — tracks which tickers have been
# bridge-synced in this Python process. Prevents redundant bridge syncs when
# multiple skills run for the same ticker (valuation → financials → historical).
# [P1 #8] Protected by _bridge_lock to prevent TOCTOU race in concurrent execution.
_BRIDGE_SYNCED_TICKERS: set[str] = set()
_bridge_lock = threading.Lock()

# [P1 #6] HEAD check cache — 60min TTL. Prevents 104 redundant HTTP HEAD requests
# when running all 13 dashboards (13 skills × 8 CVM sources = 104 HEADs).
_HEAD_CACHE: dict[str, tuple[bool, float]] = {}  # key → (has_new_data, timestamp)
_HEAD_TTL = 3600  # 1 hour

# Freshness window (hours). A source is "stale" if its last sync is older
# than this, or if it has no sync_state entry at all.
SYNC_FRESHNESS_HOURS = 24


# [Phase 4 C3] Module-level sync-source registry. Was an inline dict literal
# inside _trigger_sync() (rebuilt on every call). Now built once at import
# time + exposed for runtime extension via register_sync_source().
#
# Tuple shape: (module_path, fn_name, kwargs_fn) where kwargs_fn takes 4 args
#   (current_year, prev_year, company, trace_id) and returns the kwargs dict
#   to splat into the sync function. The 4-arg signature is required because
#   the lambdas live at module scope (they can't close over _trigger_sync's
#   locals like the old in-function literal did).
#
# Kept as a dict literal (NOT populated via register_sync_source() calls)
# intentionally — tests/test_sync_guard_mapping.py greps the source file
# text for `"source_key": (` lines. Per-source register_sync_source() calls
# would break that test (Option B in the investigation, rejected).
# register_sync_source() is provided as a public extension point for
# out-of-tree / plugin sources.
KwargsFn = Callable[[int, int, "str | None", str], dict]
_SYNC_REGISTRY: dict[str, tuple[str, str, KwargsFn]] = {
    "dfp":          ("data_sources.cvm.dfp.sync_engine", "sync",
                     lambda cy, py, co, ti: {"years": [cy, py], "force": True, "trace_id": ti, "verbose": False}),
    "itr":          ("data_sources.cvm.itr.sync_engine", "sync",
                     lambda cy, py, co, ti: {"years": [cy, py], "force": True, "trace_id": ti, "verbose": False}),
    "fre":          ("data_sources.cvm.fre.sync_engine", "sync",
                     lambda cy, py, co, ti: {"years": [cy, py], "force": True, "trace_id": ti, "verbose": False}),
    "ipe":          ("data_sources.cvm.ipe.sync_engine", "sync",
                     lambda cy, py, co, ti: {"years": [cy, py], "force": True, "trace_id": ti, "verbose": False}),
    "fca":          ("data_sources.cvm.fca.sync_engine", "sync",
                     lambda cy, py, co, ti: {"year": cy, "force": True}),
    "cad":          ("data_sources.cvm.cad.sync_engine", "sync",
                     lambda cy, py, co, ti: {"force": True, "trace_id": ti, "verbose": False}),
    "vlmo":         ("data_sources.cvm.vlmo.sync_engine", "sync",
                     lambda cy, py, co, ti: {"year": cy, "force": True}),
    "cgvn":         ("data_sources.cvm.cgvn.sync_engine", "sync",
                     lambda cy, py, co, ti: {"year": cy, "force": True}),
    "bridge":       ("data_sources.cvm.bridge.sync_engine", "sync",
                     lambda cy, py, co, ti: {"ticker": co or "", "force": False, "trace_id": ti}),
    "cotahist":     ("data_sources.b3.cotahist.sync_engine", "sync",
                     lambda cy, py, co, ti: {"year": cy, "force": False, "trace_id": ti}),
    "b3_dividends": ("data_sources.b3.dividends.sync_engine", "sync",
                     lambda cy, py, co, ti: {"force": True, "trace_id": ti}),
    "brapi":        ("data_sources.b3.brapi.sync_engine", "sync_tickers",
                     lambda cy, py, co, ti: {"force": True}),
    # [new commit] BCB SGS sync — REQUIRED_SOURCES in historical includes "sgs"
    # but sync_map had no entry, so every dashboard run failed the sgs sync
    # silently with "unknown source 'sgs'". This meant Selic/CDI/IPCA data
    # could go stale indefinitely. sync_all(force=True) re-fetches all series
    # (force=True so the guard's staleness check doesn't no-op the refresh).
    "sgs":          ("data_sources.bcb.sgs.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1.4] BCB Focus sync — REQUIRED_SOURCES in macro includes "focus"
    # (added in macro v1.4 alongside the Expectativas Focus tab). Mirrors
    # the sgs entry: sync_all(force=True) re-fetches all 4 indicators
    # (IPCA, Selic, PIB, Cambio) from the Olinda OData API.
    "focus":        ("data_sources.bcb.focus.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1] DDM Inflation sync - REQUIRED_SOURCES in skills/ddm/inflation
    # includes "ddm-inflation". Mirrors the sgs + focus entries:
    # sync_all(force=True) re-fetches all 3 indices (IGP-M, IPCA, INPC)
    # from the HTML scraper.
    # [v2 fix B3] Key renamed from "ddm" to "ddm-inflation" to match
    # the skill's REQUIRED_SOURCES (was reverted in 32e5ab9, causing
    # _trigger_sync("ddm-inflation") to fail with "unknown source").
    "ddm-inflation": ("data_sources.ddm.inflation.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1] DDM Juros sync - separate sync_map entry for the juros subdomain
    # (Selic, Meta Selic, CDI). Mirrors the ddm entry: sync_all(force=True)
    # re-fetches all 3 juros indices from the HTML scraper + derives the
    # historical series (month_value, media_no_ano, media_12m) from the
    # monthly matrix. Skills may explicitly request this via
    # _trigger_sync("ddm-juros") or list it in REQUIRED_SOURCES.
    "ddm-juros":    ("data_sources.ddm.juros.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1] DDM Poupanca sync - separate sync_map entry for the poupanca
    # subdomain (Poupanca - Brazilian savings account). Mirrors the
    # ddm + ddm-juros entries: sync_all(force=True) re-fetches the
    # poupanca page from the HTML scraper + derives the historical
    # series (month_value, acumulado_no_ano, acumulado_12m) from the
    # monthly matrix using SUM (NOT AVERAGE like juros - poupanca
    # monthly yield is a percentage return, so summing produces the
    # cumulative return). Skills may explicitly request this via
    # _trigger_sync("ddm-poupanca") or list it in REQUIRED_SOURCES.
    "ddm-poupanca": ("data_sources.ddm.poupanca.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1] DDM Acoes sync - separate sync_map entry for the acoes
    # subdomain (B3 tradable stocks). Mirrors the ddm + ddm-juros +
    # ddm-poupanca entries: sync_all(force=True) re-fetches the single
    # /acoes page from the HTML scraper + parses the stocks table
    # (~380 rows of Ticker | Nome | Negocios | Ultima (R$) | Variacao).
    # Skills may explicitly request this via _trigger_sync("ddm-acoes")
    # or list it in REQUIRED_SOURCES. The acoes dashboard declares
    # REQUIRED_SOURCES=["ddm-acoes"] so the sync guard auto-refreshes
    # acoes.db before each dashboard run.
    "ddm-acoes":    ("data_sources.ddm.acoes.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1] DDM Focus sync - separate sync_map entry for the focus
    # subdomain (Boletim Focus market expectations survey). Mirrors
    # the ddm + ddm-juros + ddm-poupanca + ddm-acoes entries:
    # sync_all(force=True) re-fetches the single /boletim-focus page
    # (CloudFront-protected - fetcher sends full Chrome 127 browser
    # headers) + parses the 4 yearly tables (2026-2029) of 12
    # indicators each. Skills may explicitly request this via
    # _trigger_sync("ddm-focus") or list it in REQUIRED_SOURCES. The
    # focus dashboard declares REQUIRED_SOURCES=["ddm-focus"] so the
    # sync guard auto-refreshes focus.db before each dashboard run.
    "ddm-focus":    ("data_sources.ddm.focus.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v1] DDM Fluxo sync - separate sync_map entry for the fluxo
    # subdomain (B3 investment flow by investor type). Mirrors the
    # ddm + ddm-juros + ddm-poupanca + ddm-acoes + ddm-focus entries:
    # sync_all(force=True) re-fetches the single /fluxo page
    # (CloudFront-protected - fetcher sends full Chrome 127 browser
    # headers) + parses the 1 table (~247 daily rows: Data |
    # Estrangeiro | Institucional | Pessoa fisica | Inst. Financeira
    # | Outros). Values are parsed from PT-BR format ("1.582,35 mi")
    # to REAL (millions R$) at the fetcher boundary. Skills may
    # explicitly request this via _trigger_sync("ddm-fluxo") or list
    # it in REQUIRED_SOURCES. The fluxo dashboard declares
    # REQUIRED_SOURCES=["ddm-fluxo"] so the sync guard auto-refreshes
    # fluxo.db before each dashboard run.
    "ddm-fluxo":     ("data_sources.ddm.fluxo.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v2 fix B2] DDM Dividends sync - was silently removed from sync_map
    # during the 30fa822 rebase (focus commit). The dividends skill
    # declares REQUIRED_SOURCES=["ddm-dividends"], so without this
    # entry, _trigger_sync("ddm-dividends") returned "unknown source".
    "ddm-dividends": ("data_sources.ddm.dividends.sync_engine", "sync_all",
                     lambda cy, py, co, ti: {"force": True}),
    # [v2.0] B3 API CSV bulk download — derivatives open positions.
    # The DerivativesOpenPosition table (17 cols, ~46K rows) feeds the
    # options skill's new "Posições em Aberto" tab (open interest +
    # position breakdown by holder/writer/covered/uncovered).
    "b3-api-derivatives": ("data_sources.b3.api.sync_engine", "sync",
                     lambda cy, py, co, ti: {"table": "derivatives", "force": True, "trace_id": ti}),
    # [v2.0] B3 API CSV bulk download — instruments (master reference).
    # The InstrumentsConsolidated table (52 cols, ~169K rows) is joined
    # with derivatives on TckrSymb to enrich each option row with
    # ExrcPric (strike), XprtnDt (expiration date), OptnStyle (AMER/EURO),
    # OptnTp (Call/Put), and CrpnNm (company name).
    "b3-api-instruments": ("data_sources.b3.api.sync_engine", "sync",
                     lambda cy, py, co, ti: {"table": "instruments", "force": True, "trace_id": ti}),
}


def register_sync_source(
    source: str,
    module_path: str,
    fn_name: str,
    kwargs_fn: KwargsFn | None = None,
) -> None:
    """Register a data source for sync-guard dispatch.

    Idempotent — re-registration overwrites the previous entry.

    Args:
        source:      The dispatch key (e.g. "ddm-fluxo", "dfp", "sgs").
                     Must match the strings skills declare in their
                     REQUIRED_SOURCES list.
        module_path: Dotted Python path to the sync_engine module
                     (e.g. "data_sources.ddm.fluxo.sync_engine"). Imported
                     lazily via importlib.import_module() only when the
                     source is dispatched — registering a source does NOT
                     import its module.
        fn_name:     Attribute name to call on the module (e.g. "sync_all",
                     "sync", "sync_tickers").
        kwargs_fn:   Callable taking (current_year, prev_year, company,
                     trace_id) and returning the kwargs dict to splat into
                     the sync function. The 4-arg signature mirrors what
                     the builtin entries need (CVM sources use
                     current_year/prev_year/trace_id; bridge uses company).
                     Defaults to ``lambda *a: {"force": True}`` for sources
                     that take only ``force=True``.

    Example::

        from skills._base.sync_guard import register_sync_source
        register_sync_source(
            "b3-index", "data_sources.b3.index.sync_engine", "sync_all",
            lambda cy, py, co, ti: {"force": True},
        )
    """
    _SYNC_REGISTRY[source] = (
        module_path,
        fn_name,
        kwargs_fn or (lambda cy, py, co, ti: {"force": True}),
    )


def _source_last_sync(source: str) -> str:
    """Get the last-sync timestamp for a data source (ISO string, or "").

    Delegates to skills._freshness.get_freshness() — the consolidated
    cross-domain freshness dict (CVM + B3 + BCB + DDM all in one).
    """
    try:
        # [v2 fix B1] Import from the shared skills/_freshness.py
        # (moved from skills/cvm/_freshness.py in commit 4ebdabf).
        # The old import path pointed to a deleted module, causing
        # ImportError → silently returned "" for every source → every
        # dashboard force-synced. See review B1.
        from skills._freshness import get_freshness
        fresh = get_freshness()
        ts = fresh.get(source, "")
        if ts:
            return ts
    except Exception:
        pass
    # NOTE: A second fallback block that tried skills.cvm._freshness was
    # removed in the _base/ split — that module was deleted in commit
    # 4ebdabf (Phase 1 B1 fix moved everything to skills/_freshness.py).
    # The try/except above silently swallowed the ImportError, so the
    # block had no runtime effect. skills/_freshness.get_freshness()
    # already covers CVM sources since Phase 1 B1 restored the CVM
    # section there.
    return ""


def _parse_sync_ts(ts: str) -> datetime | None:
    """Parse a sync timestamp string to a LOCAL naive datetime.

    Handles mixed conventions in the codebase:
      - cotahist/brapi store UTC with tzinfo  (e.g. "2026-08-08T20:00:00+00:00")
      - bridge/dfp/itr store LOCAL naive     (e.g. "2026-08-08T17:00:00")

    If the timestamp has tzinfo (UTC), convert to local then strip tzinfo so
    it can be compared with datetime.now() (local naive) without producing
    negative ages.
    """
    try:
        last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if last.tzinfo is not None:
            # UTC timestamp → convert to local time, then strip tzinfo
            last = last.astimezone().replace(tzinfo=None)
        return last
    except (ValueError, TypeError):
        return None


def _source_is_stale(source: str, max_age_hours: int = SYNC_FRESHNESS_HOURS) -> bool:
    """Check if a data source is stale (last sync older than max_age_hours, or missing).

    A source is stale if:
      - Its last-sync timestamp is "" (never synced / DB missing), OR
      - Its last-sync timestamp is older than max_age_hours from now.
    """
    ts = _source_last_sync(source)
    if not ts:
        return True  # never synced
    last = _parse_sync_ts(ts)
    if last is None:
        return True  # can't parse → treat as stale
    age = datetime.now() - last
    return age > timedelta(hours=max_age_hours)


def _cvm_has_new_data(source: str, year: int) -> bool:
    """HEAD request to CVM URL — check if server has new data since last sync.

    Returns True if:
      - The remote Last-Modified header is newer than the last sync timestamp, OR
      - The HEAD request fails (network error, timeout) — safer to sync than skip.

    Returns False only if:
      - The HEAD succeeds AND Last-Modified is older than the last sync.

    Args:
        source: One of "dfp", "itr", "fca", "fre", "ipe", "vlmo", "cgvn", "cad".
        year: The year to check (e.g., 2025). Ignored for "cad" (no year in URL).
    """
    import requests
    import email.utils

    # [v4] All CVM sources now have URL maps — previously only dfp/itr/fca
    # were HEAD-checkable; fre/ipe/vlmo/cgvn/cad always returned True ("sync
    # anyway"), causing unnecessary re-downloads every route() call.
    url_map = {
        "dfp":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip",
        "itr":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip",
        "fca":  f"http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip",
        "fre":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip",
        "ipe":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip",
        "vlmo": f"http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_{year}.zip",
        "cgvn": f"http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/CGVN/DADOS/cgvn_cia_aberta_{year}.zip",
        # cad is a single CSV (no year) — always check the same URL.
        "cad":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
    }

    if source not in url_map:
        return True  # unknown source → sync anyway

    try:
        resp = requests.head(url_map[source], timeout=5, allow_redirects=True)
        remote_mtime_str = resp.headers.get("Last-Modified", "")
        if not remote_mtime_str:
            return True  # no Last-Modified header → sync
        remote_mtime = email.utils.parsedate_to_datetime(remote_mtime_str)
        # CVM's Last-Modified is UTC → convert to local naive for comparison
        if remote_mtime.tzinfo is not None:
            remote_mtime = remote_mtime.astimezone().replace(tzinfo=None)

        last_sync_str = _source_last_sync(source)
        if not last_sync_str:
            return True  # never synced → sync
        last_sync = _parse_sync_ts(last_sync_str)
        if last_sync is None:
            return True  # can't parse → sync

        return remote_mtime > last_sync
    except Exception:
        # Network error, timeout, parse error → safer to sync than skip
        return True


def _cvm_has_new_data_cached(source: str, year: int) -> bool:
    """HEAD check with 60min in-memory TTL.

    [P1 #6] Prevents 104 redundant HTTP HEAD requests when running all 13
    dashboards (13 skills × 8 CVM sources = 104 HEADs). The HEAD result
    only changes when CVM publishes new data (daily at most), so 1h TTL
    is more than enough.
    """
    import time as _time
    key = f"{source}:{year}"
    now = _time.time()

    if key in _HEAD_CACHE:
        result, ts = _HEAD_CACHE[key]
        if now - ts < _HEAD_TTL:
            return result

    result = _cvm_has_new_data(source, year)
    _HEAD_CACHE[key] = (result, now)
    return result


def _trigger_sync(source: str, company: str | None = None, trace_id: str = "") -> dict:
    """Trigger force-sync for a single data source. Returns sync result dict.

    Looks up `source` in the module-level `_SYNC_REGISTRY` (built once at
    import time, optionally extended via `register_sync_source()`), then
    imports the sync_engine module lazily + calls the registered function
    with the kwargs returned by the entry's `kwargs_fn(current_year,
    prev_year, company, trace_id)`.

    Maps source names to their sync functions with the right args:
      - DFP/ITR/FRE/IPE: sync(years=[current_year, prev_year], force=True)
      - FCA:             sync(year=current_year, force=True)
      - CAD:             sync(force=True)
      - VLMO/CGVN:       sync(year=current_year, force=True)
      - bridge:          sync(ticker=company, force=True) — only requested ticker
      - cotahist:        sync(year=current_year, force=True)
      - brapi:           sync_tickers(force=True)

    Args:
        source: One of the source names above (or any key registered via
                register_sync_source()).
        company: Ticker (for bridge sync). None for other sources.
        trace_id: Tracer ID for logging.
    """
    import traceback

    current_year = datetime.now().year
    # [v1.16 3T2025-fix] Also sync the PREVIOUS year for DFP/ITR/FRE/IPE.
    # CVM publishes quarterly ITR data throughout the year — 3T2025 (Q3) may
    # be published AFTER the initial 2025 sync ran. The old code only force-
    # synced current_year (2026), so late-published 2025 data was never
    # picked up. Now we sync both current + previous year for the 4 CVM
    # financial-statement sources (dfp/itr/fre/ipe).
    prev_year = current_year - 1

    # [Phase 4 C3] The dispatch table is now the module-level _SYNC_REGISTRY
    # (was an inline dict literal rebuilt on every call). The lambdas take
    # (current_year, prev_year, company, trace_id) explicitly because they
    # can no longer close over this function's locals.
    if source not in _SYNC_REGISTRY:
        return {"status": "error", "source": source,
                "error": f"unknown source '{source}' (no sync function mapped)"}

    module_path, fn_name, kwargs_fn = _SYNC_REGISTRY[source]
    try:
        mod = importlib.import_module(module_path)
        sync_fn = getattr(mod, fn_name)
        kwargs = kwargs_fn(current_year, prev_year, company, trace_id)
        print(f"  [sync] Force-syncing {source} (kwargs: {kwargs})...", flush=True)
        result = sync_fn(**kwargs)
        print(f"  [sync] {source} done.", flush=True)
        return {"status": "ok", "source": source, "result": result}
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  [sync] {source} FAILED: {e}", flush=True)
        return {"status": "error", "source": source,
                "error": str(e), "traceback": tb}


def ensure_fresh(
    sources: list[str],
    company: str | None = None,
    skip_sync: bool = False,
    trace_id: str = "",
) -> dict:
    """Ensure all named data sources are fresh (synced within 24h).

    For each source:
      1. Check freshness via _source_is_stale() (24h window).
      2. If stale AND not skip_sync:
         a. For CVM sources (dfp/itr/fca): HEAD check — only sync if CVM
            has new data (or HEAD fails).
         b. For other sources: sync directly.
      3. On sync failure: record error but DON'T raise (proceed with stale).
      4. Record result.

    Args:
        sources: List of source names (e.g., ["dfp", "itr", "bridge"]).
        company: Ticker (for bridge sync — only syncs this ticker).
        skip_sync: If True, only check — don't trigger sync.
        trace_id: Tracer ID for sync logging.

    Returns:
        {"synced": [...], "fresh": [...], "errors": [...], "skipped": [...]}

    Escape hatches (sync is NEVER triggered):
      - CVM_SKIP_SYNC=1 env var
      - skip_sync=True kwarg
    """
    # Global escape hatch for tests
    if os.environ.get("CVM_SKIP_SYNC") == "1":
        skip_sync = True

    synced: list[str] = []
    fresh: list[str] = []
    errors: list[dict] = []
    skipped: list[str] = []

    # [v2.1] CVM sources ALWAYS get a HEAD check against the server — not
    # just when the local DB is >24h old. This catches new quarterly filings
    # published within the 24h window. Non-CVM sources (cotahist, brapi,
    # bridge, sgs, index) keep the 24h freshness window.
    _CVM_SOURCES = {"dfp", "itr", "fca", "fre", "ipe", "cad", "vlmo", "cgvn"}

    # [v2.0 fix] ITR is quarterly — CVM adds new filings to the same ZIP file
    # throughout the year without updating the Last-Modified header. So the
    # HEAD check says "up to date" even when new quarterly data was published.
    # Fix: ITR always uses the 24h freshness window (like non-CVM sources),
    # skipping the unreliable HEAD check. DFP/FCA are annual (published once
    # a year) — the HEAD check works for them.
    _CVM_HEAD_SKIP = {"itr"}  # sources that skip HEAD check, use 24h window

    # [Tier 0 #2] Parallelize CVM HEAD checks — was 8 sequential HTTP requests
    # (3-40s), now concurrent (~5s max). The sync itself stays sequential
    # (same DB files), but the HEAD check is the slow part.
    cvm_sources_in_list = [s for s in sources if s in _CVM_SOURCES]
    cvm_head_results: dict[str, bool] = {}  # source → has_new_data

    if cvm_sources_in_list and not skip_sync:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        current_year = datetime.now().year
        print(f"  [sync] Checking CVM HEAD for {len(cvm_sources_in_list)} sources (parallel)...", flush=True)

        def _do_head_check(src):
            return src, _cvm_has_new_data_cached(src, current_year)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_do_head_check, s): s for s in cvm_sources_in_list}
            for future in as_completed(futures):
                src, has_new = future.result()
                cvm_head_results[src] = has_new

    for source in sources:
        # CVM sources: use the parallel HEAD-check results
        # [v2.0] ITR skips HEAD check (unreliable Last-Modified) — uses 24h window
        if source in _CVM_SOURCES and source not in _CVM_HEAD_SKIP:
            if skip_sync:
                skipped.append(source)
                continue
            has_new = cvm_head_results.get(source, True)  # default True if missing
            if not has_new:
                print(f"  [sync] {source} HEAD: up to date (no sync needed)", flush=True)
                fresh.append(source)
                continue
            # CVM has new data → trigger sync
            print(f"  [sync] {source} HEAD: new data available → force-sync", flush=True)
            sync_result = _trigger_sync(source, company=company, trace_id=trace_id)
            sync_status = sync_result.get("status")
            if sync_status in ("ok", "skipped"):
                synced.append(source)
            else:
                errors.append({
                    "source": source,
                    "error": sync_result.get("error", "unknown sync error"),
                })
            continue

        # Non-CVM sources: use 24h freshness window
        # [Tier 0 #3] Bridge dedup: skip bridge sync if this ticker was already
        # synced in this Python session (valuation → financials → historical all
        # sync bridge for the same PETR4 — only the first should actually sync).
        # [P1 #8] Protected by _bridge_lock to prevent TOCTOU race.
        if source == "bridge" and company:
            with _bridge_lock:
                if company.upper() in _BRIDGE_SYNCED_TICKERS:
                    print(f"  [sync] bridge: fresh (synced earlier this session for {company})", flush=True)
                    fresh.append(source)
                    continue

        if not _source_is_stale(source):
            _ts = _source_last_sync(source)
            _age = ""
            if _ts:
                _last = _parse_sync_ts(_ts)
                if _last is not None:
                    _age_h = int((datetime.now() - _last).total_seconds() / 3600)
                    _age = f" ({_age_h}h ago)"
            print(f"  [sync] {source}: fresh{_age}", flush=True)
            fresh.append(source)
            continue

        if skip_sync:
            skipped.append(source)
            continue

        print(f"  [sync] {source}: stale (>24h) → force-sync", flush=True)
        # Trigger force-sync (blocking)
        sync_result = _trigger_sync(source, company=company, trace_id=trace_id)
        sync_status = sync_result.get("status")
        # Treat both "ok" (synced) and "skipped" (already up-to-date) as success
        if sync_status in ("ok", "skipped"):
            synced.append(source)
            # [Tier 0 #3] Record bridge sync for session dedup
            # [P1 #8] Protected by _bridge_lock
            if source == "bridge" and company:
                with _bridge_lock:
                    _BRIDGE_SYNCED_TICKERS.add(company.upper())
        else:
            errors.append({
                "source": source,
                "error": sync_result.get("error", "unknown sync error"),
            })

    return {
        "synced": synced,
        "fresh": fresh,
        "errors": errors,
        "skipped": skipped,
    }
