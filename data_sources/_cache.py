"""data_sources/_cache.py — Persistent engine result cache (cross-skill).

Provides a SQLite-backed cache layer that sits BETWEEN the data sources
(CVM/B3/BCB) and the skills. It persists engine `*_at(company, date)` results
so that when multiple skills compute the same engine for the same company
(e.g., valuation computes revenue_at("PETR4", "2024-06-30"), then financials
computes the same), the second call is a cache hit (0.001s instead of ~1s).

## Why this exists

The in-memory `engine_cache_scope` (ContextVar in skills/_base.py) only
caches within a single `route()` call. When valuation finishes and financials
starts, the in-memory cache is wiped. PETR4's engines get recomputed 5 times
across valuation + financials + historical + screener + comparison. This DB
cache eliminates that redundancy.

## Architecture

    ┌─────────────────────────────────────────────────────┐
    │  skills (valuation, financials, historical, ...)    │
    └────────────────────┬────────────────────────────────┘
                         │ calls
    ┌────────────────────▼────────────────────────────────┐
    │  skills/cvm/calculations/engines/*.py               │
    │  @engine_cached wrapper                             │
    │  ┌─────────────────────────────────────────────┐    │
    │  │ 1. In-memory cache (ContextVar)             │    │
    │  │ 2. DB cache (THIS MODULE)                   │    │
    │  │ 3. Real engine fn (queries DFP/ITR/etc.)    │    │
    │  └─────────────────────────────────────────────┘    │
    └────────────────────┬────────────────────────────────┘
                         │ reads/writes
    ┌────────────────────▼────────────────────────────────┐
    │  memory_db/cache/engine_cache.db                    │
    │  ├── engine_cache        (cached values)            │
    │  ├── engine_cache_meta   (invalidation fingerprints)│
    │  └── sync_versions       (current data versions)    │
    └─────────────────────────────────────────────────────┘

## Invalidation

Per-company fingerprint (NOT the HEAD-check timestamp, which is per-source):
  - DFP/ITR engines: MAX(versao) || '|' || MAX(data_fim_exerc) for that CNPJ
  - COTAHIST engines: MAX(refdate) for that ticker
  - BCB SGS engines: MAX(ref_date) for the series
  - FRE engines: MAX(data_referencia) for that CNPJ

If the fingerprint matches, the cache is valid. If CVM publishes a new filing
(new versao or new period), the fingerprint changes → cache miss → recompute.

## Escape hatch

CVM_SKIP_DB_CACHE=1 env var disables the DB cache entirely (for tests).

## Location

This is a SHARED HELPER (underscore prefix), not a data source domain. It
benefits all 3 data source domains (CVM, B3, BCB) — engines read from DFP/ITR
(CVM), COTAHIST (B3), and SGS (BCB). Putting it in data_sources/cvm/ would
be wrong for the B3/BCB engines.

## Usage (internal — called by skills/cvm/calculations/_registry.py)

    from data_sources._cache import get_cached, set_cached, is_valid

    if is_valid(engine_name, cnpj):
        cached = get_cached(engine_name, cnpj, date)
        if cached is not None:
            return cached["value"]

    result = real_engine_fn(company, date)
    set_cached(engine_name, cnpj, date, result)
    return result
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Path resolution ──────────────────────────────────────────────────────────

def cache_data_dir() -> Path:
    """Return the cache database directory (creates it if missing).

    Follows the same pattern as data_sources/cvm/_db.py:cvm_db_path(),
    data_sources/b3/cotahist/catalog.py:b3_data_dir(), etc.
    Uses cfg.memory_root / "cache".
    """
    try:
        from core.config import cfg
        memory_root = getattr(cfg, "memory_root", None)
    except Exception:
        memory_root = None

    if memory_root:
        d = Path(memory_root) / "cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # Fallback: walk up from cwd
    p = Path.cwd()
    for _ in range(5):
        candidate = p / "memory_db" / "cache"
        if candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        p = p.parent

    # Last resort: create in cwd
    d = Path.cwd() / "memory_db" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    """Return the path to engine_cache.db."""
    return cache_data_dir() / "engine_cache.db"


# ── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS engine_cache (
    engine_name   TEXT NOT NULL,
    cnpj          TEXT NOT NULL,
    date          TEXT NOT NULL,
    value         REAL,
    computed_at   TEXT NOT NULL,
    PRIMARY KEY (engine_name, cnpj, date)
);

CREATE INDEX IF NOT EXISTS idx_engine_cnpj ON engine_cache(cnpj);

CREATE TABLE IF NOT EXISTS engine_periods (
    engine_name   TEXT NOT NULL,
    cnpj          TEXT NOT NULL,
    args_suffix   TEXT NOT NULL DEFAULT '',
    periods_json  TEXT NOT NULL,
    computed_at   TEXT NOT NULL,
    PRIMARY KEY (engine_name, cnpj, args_suffix)
);

CREATE TABLE IF NOT EXISTS engine_cache_meta (
    engine_name     TEXT NOT NULL,
    cnpj            TEXT NOT NULL,
    source_version  TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    PRIMARY KEY (engine_name, cnpj)
);
"""


# ── Connection (WAL + per-thread connection pool) ────────────────────────────
# [P2 #10] Drop the global threading.Lock — WAL mode allows concurrent readers
# + 1 writer. Per-thread connection pool avoids opening/closing on every call.

import threading as _threading

_tls = _threading.local()


def connect(read_only: bool = False) -> sqlite3.Connection:
    """Open or reuse a connection to engine_cache.db.

    Uses per-thread connection pooling (threading.local) + WAL mode for
    concurrent read access without a global lock.

    Args:
        read_only: If True, opens in read-only mode (for get/is_valid queries).
                   If False, opens for writes (creates the DB + schema if missing).
    """
    cache_key = f"{'ro' if read_only else 'rw'}"
    conn = getattr(_tls, cache_key, None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            # Connection went stale — recreate
            try:
                conn.close()
            except Exception:
                pass
            conn = None

    path = db_path()
    if read_only:
        if not path.exists():
            raise FileNotFoundError(f"Cache DB not found at {path}")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                               check_same_thread=False, timeout=10)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
        conn.commit()
    conn.row_factory = sqlite3.Row
    setattr(_tls, cache_key, conn)
    return conn


# Lock for fingerprint cache + bridge dedup (NOT for DB ops — WAL handles that)
_aux_lock = _threading.Lock()


# ── Fingerprint cache (60s TTL) ──────────────────────────────────────────────
# [P1 #5] Cache fingerprints in-memory so we don't open DFP/ITR DBs on every
# is_valid() call. The fingerprint only changes when CVM publishes a new filing
# (quarterly max), so 60s TTL eliminates 99% of fingerprint queries.

_FP_TTL = 60  # seconds
_fp_cache: dict[str, tuple[str | None, float]] = {}  # key → (fingerprint, timestamp)


def _get_cached_fingerprint(engine_name: str, company: str) -> str | None:
    """Get fingerprint with 60s in-memory TTL."""
    key = f"{engine_name}|{company}"
    now = _threading.get_ident()  # not used for time, just to get module
    import time as _time
    now = _time.time()

    with _aux_lock:
        if key in _fp_cache:
            fp, ts = _fp_cache[key]
            if now - ts < _FP_TTL:
                return fp

    fp = get_current_fingerprint_uncached(engine_name, company)

    with _aux_lock:
        _fp_cache[key] = (fp, now)

    return fp


# ── Escape hatch ─────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Check if the DB cache is enabled (not disabled via env var)."""
    return os.environ.get("CVM_SKIP_DB_CACHE") != "1"


# ── Company → CNPJ resolution ────────────────────────────────────────────────

_cnpj_cache: dict[str, str] = {}
_cnpj_cache_lock = threading.Lock()


def resolve_cnpj(company: str) -> str | None:
    """Resolve a company identifier (ticker/name/CNPJ) to its CNPJ.

    Uses the bridge resolver (FCA first, then bridge.db). Results are cached
    in-process to avoid repeated bridge lookups for the same company.

    Returns None if the company can't be resolved.
    """
    if not company or not company.strip():
        return None

    company = company.strip()

    # If it's already a 14-digit CNPJ, use it directly
    digits = "".join(c for c in company if c.isdigit())
    if len(digits) == 14:
        return digits

    # Check in-process cache
    with _cnpj_cache_lock:
        if company in _cnpj_cache:
            return _cnpj_cache[company]

    # Resolve via bridge
    try:
        from data_sources.cvm._bridge import _resolve_via_bridge
        cnpj, _ = _resolve_via_bridge(company)
        if cnpj:
            # Normalize to digits only
            cnpj_digits = "".join(c for c in cnpj if c.isdigit())
            if len(cnpj_digits) == 14:
                with _cnpj_cache_lock:
                    _cnpj_cache[company] = cnpj_digits
                return cnpj_digits
    except Exception:
        pass

    return None


# ── Fingerprint queries ──────────────────────────────────────────────────────

def _get_dfp_fingerprint(cnpj: str) -> str | None:
    """Get the data fingerprint for a company in DFP/ITR.

    Returns MAX(versao) || '|' || MAX(data_fim_exerc) for that CNPJ.
    This changes when: (1) a new filing version is published (versao++),
    or (2) a new period is added (data_fim_exerc changes).
    """
    try:
        from data_sources.cvm._db import _get_company_fingerprint
        return _get_company_fingerprint(cnpj)
    except Exception:
        return None


def _get_cotahist_fingerprint(ticker: str) -> str | None:
    """Get the data fingerprint for a ticker in COTAHIST.

    Returns MAX(refdate) — the latest price date. Changes daily.
    """
    try:
        from data_sources.b3.cotahist.catalog import connect as connect_cot
        conn = connect_cot(read_only=True)
        try:
            row = conn.execute(
                "SELECT MAX(refdate) as max_date FROM daily_prices WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            return row["max_date"] if row and row["max_date"] else None
        finally:
            conn.close()
    except Exception:
        return None


def _get_sgs_fingerprint(series_code: int = 11) -> str | None:
    """Get the data fingerprint for a BCB SGS series.

    Returns MAX(ref_date) — the latest observation date. Changes daily.
    """
    try:
        from data_sources.bcb.sgs.catalog import connect as connect_sgs
        conn = connect_sgs(read_only=True)
        try:
            row = conn.execute(
                "SELECT MAX(ref_date) as max_date FROM series_observations "
                "WHERE series_code = ?",
                (series_code,),
            ).fetchone()
            return row["max_date"] if row and row["max_date"] else None
        finally:
            conn.close()
    except Exception:
        return None


def _get_fre_fingerprint(cnpj: str) -> str | None:
    """Get the data fingerprint for a company in FRE.

    Returns MAX(data_referencia) for that CNPJ. Changes quarterly.
    """
    try:
        from data_sources.cvm._db import fre_db_path
        path = fre_db_path()
        if not path.exists():
            return None
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            # FRE documentos table has cnpj + data_referencia
            row = conn.execute(
                "SELECT MAX(data_referencia) as max_date FROM documentos WHERE cnpj = ?",
                (cnpj,),
            ).fetchone()
            return row["max_date"] if row and row["max_date"] else None
        finally:
            conn.close()
    except Exception:
        return None


# ── Engine → source mapping ──────────────────────────────────────────────────

# Maps engine_name → (source_type, resolver_args)
# source_type determines which fingerprint query to use.
# This is populated lazily from the EngineSpec.source field.
_ENGINE_SOURCE_MAP: dict[str, str] = {
    # DFP+ITR engines (24)
    "revenue": "dfp", "earnings": "dfp", "ebit": "dfp", "ebt": "dfp",
    "cogs": "dfp", "gross_profit": "dfp", "tax": "dfp", "financial_result": "dfp",
    "pl": "dfp", "debt": "dfp", "cash": "dfp", "total_assets": "dfp",
    "current_assets": "dfp", "inventory": "dfp", "receivables": "dfp",
    "ppe": "dfp", "intangibles": "dfp", "payables": "dfp",
    "current_liabilities": "dfp",
    "operating_cf": "dfp", "investing_cf": "dfp", "financing_cf": "dfp",
    "capex": "dfp", "da": "dfp",
    # DVA engines (10) — also DFP+ITR
    "dividends_paid": "dfp", "interest_paid": "dfp", "total_tax": "dfp",
    "value_added": "dfp", "va_gross": "dfp", "va_inputs": "dfp",
    "va_net": "dfp", "va_retentions": "dfp", "va_revenue": "dfp",
    "va_received": "dfp",
    # COTAHIST engines
    "price": "cotahist", "beta": "cotahist",
    # BCB SGS engines
    "selic": "sgs",
    # FRE engines
    "shares": "fre",
    # B3 dividends engine — uses cotahist-style (per-ticker)
    "dividends": "dividends",
}

# [P1 #7] BCB SGS engine → series code mapping
_SGS_ENGINE_TO_SERIES: dict[str, int] = {
    "selic": 11,
}


def _get_dividends_fingerprint(ticker: str) -> str | None:
    """Returns MAX(data_pagamento) for dividends — only changes when a new dividend is paid."""
    try:
        from data_sources.b3.dividends.catalog import connect as connect_div
        conn = connect_div(read_only=True)
        try:
            row = conn.execute(
                "SELECT MAX(data_pagamento) as max_date FROM proventos WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            return row["max_date"] if row and row["max_date"] else None
        finally:
            conn.close()
    except Exception:
        return None


def get_current_fingerprint_uncached(engine_name: str, company: str) -> str | None:
    """Get the current data fingerprint for an engine + company (no TTL cache).

    Returns a string like "3|2025-12-31|47|1250" (DFP) or "2026-08-09" (COTAHIST).
    Returns None if the fingerprint can't be determined (→ cache miss).
    """
    source = _ENGINE_SOURCE_MAP.get(engine_name, "dfp")

    if source == "dfp":
        cnpj = resolve_cnpj(company)
        if not cnpj:
            return None
        return _get_dfp_fingerprint(cnpj)
    elif source == "cotahist":
        ticker = company.strip().upper()
        return _get_cotahist_fingerprint(ticker)
    elif source == "dividends":
        ticker = company.strip().upper()
        return _get_dividends_fingerprint(ticker)
    elif source == "sgs":
        series_code = _SGS_ENGINE_TO_SERIES.get(engine_name, 11)
        return _get_sgs_fingerprint(series_code)
    elif source == "fre":
        cnpj = resolve_cnpj(company)
        if not cnpj:
            return None
        return _get_fre_fingerprint(cnpj)
    else:
        return None


def get_current_fingerprint(engine_name: str, company: str) -> str | None:
    """Get the current data fingerprint (with 60s in-memory TTL cache)."""
    return _get_cached_fingerprint(engine_name, company)


# ── Strict JSON encoder ──────────────────────────────────────────────────────
# [P1 #5] Replace default=str with a strict encoder that raises on unknown types
# instead of silently stringifying them (which could corrupt the cache).

class _StrictJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        raise TypeError(
            f"Object of type {type(obj).__name__} is not JSON serializable. "
            f"Engine periods must return list[dict] of str/float/int values."
        )


# ── Cache read/write ─────────────────────────────────────────────────────────

def is_valid(engine_name: str, company: str) -> bool:
    """Check if the cached engine data for this company is still valid.

    Compares the current data fingerprint with the cached fingerprint in
    engine_cache_meta. If they match, the cache is valid.
    """
    if not is_enabled():
        return False

    cnpj = resolve_cnpj(company)
    if not cnpj:
        return False

    current_fp = get_current_fingerprint(engine_name, company)
    if current_fp is None:
        return False  # can't determine → don't trust cache

    try:
        conn = connect(read_only=True)
        row = conn.execute(
            "SELECT source_version FROM engine_cache_meta "
            "WHERE engine_name = ? AND cnpj = ?",
            (engine_name, cnpj),
        ).fetchone()
        if row is None:
            return False  # no cache entry → miss
        return row["source_version"] == current_fp
    except (FileNotFoundError, Exception):
        return False


def get_cached(engine_name: str, company: str, date: str) -> dict | None:
    """Get a cached engine value.

    Returns {"value": float|None, "computed_at": str} or None if not cached.
    Does NOT check validity — caller should call is_valid() first.
    """
    if not is_enabled():
        return None

    cnpj = resolve_cnpj(company)
    if not cnpj:
        return None

    try:
        conn = connect(read_only=True)
        row = conn.execute(
            "SELECT value, computed_at FROM engine_cache "
            "WHERE engine_name = ? AND cnpj = ? AND date = ?",
            (engine_name, cnpj, str(date)),
        ).fetchone()
        if row is None:
            return None
        return {"value": row["value"], "computed_at": row["computed_at"]}
    except (FileNotFoundError, Exception):
        return None


def set_cached(engine_name: str, company: str, date: str, value: float | None) -> None:
    """Write an engine value to the cache + update the meta fingerprint."""
    if not is_enabled():
        return

    cnpj = resolve_cnpj(company)
    if not cnpj:
        return

    current_fp = get_current_fingerprint(engine_name, company)
    if current_fp is None:
        return

    now = datetime.now().isoformat()

    try:
        conn = connect(read_only=False)
        conn.execute(
            "INSERT OR REPLACE INTO engine_cache "
            "(engine_name, cnpj, date, value, computed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (engine_name, cnpj, str(date), value, now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO engine_cache_meta "
            "(engine_name, cnpj, source_version, cached_at) "
            "VALUES (?, ?, ?, ?)",
            (engine_name, cnpj, current_fp, now),
        )
        conn.commit()
    except Exception:
        pass  # never break the engine call on cache write failure


# ── Cache read/write — *_periods() (JSON-serialized lists) ───────────────────

def get_cached_periods(engine_name: str, company: str, args_suffix: str = "") -> list | dict | None:
    """Get cached *_periods() result (JSON-deserialized).

    Args:
        engine_name: Engine name (e.g., "price")
        company: Company ticker/CNPJ
        args_suffix: For multi-arg periods functions (e.g., price_series(ticker, date_from, date_to)),
                     this is the serialized suffix of extra args (e.g., "2021-01-01_2026-01-01").
                     For 1-arg periods functions, this is "" (empty string).
    """
    if not is_enabled():
        return None
    cnpj = resolve_cnpj(company)
    if not cnpj:
        return None
    try:
        conn = connect(read_only=True)
        row = conn.execute(
            "SELECT periods_json FROM engine_periods "
            "WHERE engine_name = ? AND cnpj = ? AND args_suffix = ?",
            (engine_name, cnpj, args_suffix),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["periods_json"])
    except (FileNotFoundError, Exception):
        return None


def set_cached_periods(engine_name: str, company: str, periods: list | dict,
                       args_suffix: str = "") -> None:
    """Write *_periods() result to cache (JSON-serialized with strict encoder)."""
    if not is_enabled():
        return
    cnpj = resolve_cnpj(company)
    if not cnpj:
        return
    current_fp = get_current_fingerprint(engine_name, company)
    if current_fp is None:
        return
    now = datetime.now().isoformat()
    try:
        periods_json = json.dumps(periods, cls=_StrictJSONEncoder)
        conn = connect(read_only=False)
        conn.execute(
            "INSERT OR REPLACE INTO engine_periods "
            "(engine_name, cnpj, args_suffix, periods_json, computed_at) VALUES (?, ?, ?, ?, ?)",
            (engine_name, cnpj, args_suffix, periods_json, now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO engine_cache_meta "
            "(engine_name, cnpj, source_version, cached_at) VALUES (?, ?, ?, ?)",
            (engine_name, cnpj, current_fp, now),
        )
        conn.commit()
    except Exception:
        pass  # never break on cache write failure


# ── Maintenance ──────────────────────────────────────────────────────────────

def clear_cache(engine_name: str | None = None, cnpj: str | None = None) -> int:
    """Clear cache entries. Returns count of deleted rows."""
    try:
        conn = connect(read_only=False)
        clauses = []
        params = []
        if engine_name:
            clauses.append("engine_name = ?")
            params.append(engine_name)
        if cnpj:
            clauses.append("cnpj = ?")
            params.append(cnpj)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        cur = conn.execute(f"DELETE FROM engine_cache {where}", params)
        conn.execute(f"DELETE FROM engine_periods {where}", params)
        conn.execute(f"DELETE FROM engine_cache_meta {where}", params)
        conn.commit()
        return cur.rowcount
    except Exception:
        return 0


def cache_stats() -> dict:
    """Return cache statistics for monitoring."""
    try:
        conn = connect(read_only=True)
        total = conn.execute("SELECT COUNT(*) as n FROM engine_cache").fetchone()["n"]
        periods_total = conn.execute("SELECT COUNT(*) as n FROM engine_periods").fetchone()["n"]
        engines = conn.execute("SELECT COUNT(DISTINCT engine_name) as n FROM engine_cache").fetchone()["n"]
        companies = conn.execute("SELECT COUNT(DISTINCT cnpj) as n FROM engine_cache").fetchone()["n"]
        return {
            "total_at_entries": total,
            "total_periods_entries": periods_total,
            "engines_cached": engines,
            "companies_cached": companies,
            "db_path": str(db_path()),
        }
    except Exception:
        return {"total_at_entries": 0, "total_periods_entries": 0,
                "engines_cached": 0, "companies_cached": 0,
                "db_path": str(db_path())}
