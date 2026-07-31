"""skills/cvm/calculations/_materialized.py — Pre-computed ratios table (F8).

Stores the result of compute_all_ratios() in a SQLite table so subsequent
calls for the same (ticker, date) are single-row lookups instead of 35
engine calls.

SCHEMA
------
Table ``ratios_materialized`` in ``memory_db/cvm/ratios.db``:

    CREATE TABLE ratios_materialized (
        ticker        TEXT NOT NULL,
        date          TEXT NOT NULL,           -- YYYY-MM-DD (point-in-time)
        metric_name   TEXT NOT NULL,           -- canonical metric name (e.g. "roe")
        value         REAL,                    -- may be NULL (metric computed but None)
        computed_at   TEXT NOT NULL,           -- ISO timestamp of materialization
        PRIMARY KEY (ticker, date, metric_name)
    );
    CREATE INDEX idx_ratios_ticker_date ON ratios_materialized(ticker, date);

Normalized (long format) — one row per (ticker, date, metric). Matches the
`contas` table pattern used everywhere else in data_sources/. Adding a new
metric = INSERT, not ALTER TABLE.

WHY ONLY STABLE FUNDAMENTALS (not growth, not price-based)
----------------------------------------------------------
- **Price-based** (valuation, per_share): depend on daily COTAHIST price.
  A materialized row computed at sync time (quarterly) would be stale for
  price-based metrics within hours. So these stay live.
- **Growth** (revenue_growth_3m, etc.): lookback-window-dependent. The
  value depends on WHEN it's evaluated relative to available periods.
  Materializing bakes in a specific evaluation date, which risks the
  staleness problem we just fixed with gap-tolerance logic in v1.8.
  So growth stays live.

The materialized categories are:
  - profitability (ROE, ROA, ROIC, margins)
  - liquidity (current/quick/cash ratio, working capital)
  - leverage (D/E, net debt/EBITDA, interest coverage, cash flow to debt)
  - efficiency (turnover ratios, capex/revenue)
  - tax (effective tax rate)

READ PATH
---------
compute_all_ratios() checks the materialized table first for stable
fundamental metrics. If rows exist for (ticker, date), it uses them + only
computes the remaining (price-based + growth + any missing) live.

WRITE PATH (event-driven, NOT time-based)
-----------------------------------------
materialize_ratios(company, date) computes all stable fundamentals for a
single (company, date) and upserts into the table. Called by:
  - ensure_fresh() after a successful force-sync (event-driven invalidation)
  - Manual trigger: ``materialize_ratios("PETR4", "2024-06-30")``

A materialized row is only as good as the DFP/ITR data it was computed from.
Re-materializing happens immediately after sync completes — no time-based
staleness window (per LLM review consensus).

ESCAPE HATCH
------------
CVM_SKIP_MATERIALIZED=1 env var disables the read path (forces live
computation). Useful for tests + debugging.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Database path ────────────────────────────────────────────────────────────

def _ratios_db_path() -> Path:
    """Return the path to the ratios materialized database.

    Co-located with other CVM databases in memory_db/cvm/ratios.db.
    """
    try:
        from data_sources.cvm._db import cvm_db_path
        return cvm_db_path() / "ratios.db"
    except Exception:
        # Fallback for test environments where cvm_db_path fails
        d = Path.cwd() / "memory_db" / "cvm"
        d.mkdir(parents=True, exist_ok=True)
        return d / "ratios.db"


# ── Thread-local connection pooling ──────────────────────────────────────────
# [Qwen P1] Avoid opening a new SQLite connection for every materialized-ratio
# read. Thread-local ensures each thread gets its own connection (SQLite
# connections are NOT thread-safe by default).

_ratios_conn: threading.local = threading.local()


def _get_ratios_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection to ratios.db.

    Creates the connection + schema on first access per thread. Sets WAL
    journal mode for better concurrent read performance.
    """
    if not hasattr(_ratios_conn, "conn"):
        path = _ratios_db_path()
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        # WAL mode for better concurrent read performance
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass  # WAL not supported (e.g., :memory:) — ignore
        conn.executescript(_SCHEMA)
        conn.commit()
        _ratios_conn.conn = conn
    return _ratios_conn.conn


# ── Schema ──────────────────────────────────────────────────────────────────

# Fundamental metric categories (materialized; no price dependency).
# Price-based categories (valuation, per_share) stay live because they
# depend on daily COTAHIST. Growth stays live because it's lookback-dependent.
MATERIALIZED_CATEGORIES = [
    "profitability", "liquidity", "leverage",
    "efficiency", "tax",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ratios_materialized (
    ticker        TEXT NOT NULL,
    date          TEXT NOT NULL,
    metric_name   TEXT NOT NULL,
    value         REAL,
    computed_at   TEXT NOT NULL,
    PRIMARY KEY (ticker, date, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_ratios_ticker_date
    ON ratios_materialized(ticker, date);
"""


# ── Write path ───────────────────────────────────────────────────────────────

def materialize_ratios(company: str, date: str) -> dict:
    """Compute + store all stable fundamental metrics for (company, date).

    Walks the calculations registry's METRICS dict, filters to
    MATERIALIZED_CATEGORIES, computes each via ratio_fn (inside an
    engine_cache_scope so shared engines are queried once), and upserts
    into the ratios_materialized table.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD (the point-in-time date for the ratios).

    Returns:
        {"status": "ok", "ticker": company, "date": date,
         "materialized_count": N, "errors": [...]}
    """
    from skills.cvm.calculations._registry import METRICS
    from skills._base import engine_cache_scope

    now_iso = datetime.now().isoformat()
    materialized = 0
    errors: list[dict] = []

    rows: list[tuple] = []
    with engine_cache_scope():
        for name, spec in METRICS.items():
            if spec.category not in MATERIALIZED_CATEGORIES:
                continue
            try:
                value = spec.ratio_fn(company, date)
                rows.append((company, date, name, value, now_iso))
                materialized += 1
            except Exception as e:
                errors.append({"metric": name, "error": str(e)})

    if rows:
        conn = _get_ratios_conn()
        conn.executemany(
            """INSERT OR REPLACE INTO ratios_materialized
               (ticker, date, metric_name, value, computed_at)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    return {
        "status": "ok",
        "ticker": company,
        "date": date,
        "materialized_count": materialized,
        "errors": errors,
    }


def materialize_for_companies(
    companies: list[str], date: str,
) -> dict:
    """Materialize ratios for multiple companies at a given date.

    Used by the sync hook after DFP/ITR/FRE sync. Failures per-company
    are logged but don't abort the batch.

    Returns:
        {"status": "ok", "date": date, "total": N, "succeeded": M,
         "failed": [...]}
    """
    succeeded = 0
    failed: list[dict] = []
    for company in companies:
        try:
            r = materialize_ratios(company, date)
            if r.get("status") == "ok":
                succeeded += 1
            else:
                failed.append({"company": company, "error": r.get("error", "?")})
        except Exception as e:
            failed.append({"company": company, "error": str(e)})

    return {
        "status": "ok",
        "date": date,
        "total": len(companies),
        "succeeded": succeeded,
        "failed": failed,
    }


# ── Read path ────────────────────────────────────────────────────────────────

def get_materialized(
    company: str, date: str,
) -> dict[str, float | None] | None:
    """Get materialized fundamental ratios for (company, date) if they exist.

    Returns None if:
      - CVM_SKIP_MATERIALIZED=1 env var is set (force live), OR
      - No materialized row exists for (company, date).

    Otherwise returns a dict {metric_name: value} for all materialized
    metrics for this (company, date). Values may be None (the metric was
    computed but returned None).

    NOTE: No time-based staleness check. A materialized row is valid until
    explicitly invalidated by a re-materialization (event-driven, on sync).
    This is per LLM review consensus — don't build two independent
    staleness clocks (one for source data, one for materialized ratios)
    when one derives cleanly from the other.
    """
    if os.environ.get("CVM_SKIP_MATERIALIZED") == "1":
        return None

    try:
        conn = _get_ratios_conn()
        rows = conn.execute(
            """SELECT metric_name, value FROM ratios_materialized
               WHERE ticker = ? AND date = ?""",
            (company, date),
        ).fetchall()
        if not rows:
            return None
        return {r["metric_name"]: r["value"] for r in rows}
    except Exception:
        return None


# ── Sync hook ────────────────────────────────────────────────────────────────

def on_sync_complete(source: str, company: str | None = None) -> dict:
    """Hook called after a data source force-sync completes.

    Re-materializes ratios for the given company (event-driven invalidation).
    If company is None, skips (caller should pass the requested company).

    Args:
        source: The data source that just synced (e.g., "dfp", "itr").
        company: Ticker/CNPJ to materialize. If None, skips.

    Returns:
        {"status": "ok", "source": source, "materialized": {...} or None}
    """
    if not company:
        return {"status": "ok", "source": source, "materialized": None}

    today = datetime.now().date().isoformat()
    try:
        result = materialize_ratios(company, today)
        return {"status": "ok", "source": source, "materialized": result}
    except Exception as e:
        return {"status": "error", "source": source,
                "materialized_error": str(e)}


# ── Maintenance ──────────────────────────────────────────────────────────────

def clear_materialized(company: str | None = None) -> int:
    """Clear materialized rows (all, or for a specific company).

    Returns the number of rows deleted.
    """
    conn = _get_ratios_conn()
    if company:
        cur = conn.execute(
            "DELETE FROM ratios_materialized WHERE ticker = ?",
            (company,),
        )
    else:
        cur = conn.execute("DELETE FROM ratios_materialized")
    conn.commit()
    return cur.rowcount


def materialized_stats() -> dict:
    """Return stats about the materialized table (for diagnostics)."""
    try:
        conn = _get_ratios_conn()
        total = conn.execute(
            "SELECT COUNT(*) as n FROM ratios_materialized"
        ).fetchone()["n"]
        distinct_tickers = conn.execute(
            "SELECT COUNT(DISTINCT ticker) as n FROM ratios_materialized"
        ).fetchone()["n"]
        distinct_dates = conn.execute(
            "SELECT COUNT(DISTINCT date) as n FROM ratios_materialized"
        ).fetchone()["n"]
        latest = conn.execute(
            "SELECT MAX(computed_at) as ts FROM ratios_materialized"
        ).fetchone()["ts"]
        return {
            "total_rows": total,
            "distinct_tickers": distinct_tickers,
            "distinct_dates": distinct_dates,
            "latest_computed_at": latest or "",
        }
    except Exception as e:
        return {"error": str(e)}
