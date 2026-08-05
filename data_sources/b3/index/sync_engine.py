"""data_sources/b3/index/sync_engine.py -- Download + store B3 index compositions.

Syncs index composition from B3 indexProxy into local SQLite (index.db).
Supports:
  sync_index(code)  -- sync a single index
  sync_all()        -- sync all active indices (IBOV, SMLL, BDRX, IFIX, IDIV)

IDEMPOTENT: INSERT OR REPLACE on (index_code, ticker, ref_date) PK.
HISTORICAL: Each sync stores with the ref_date from B3, so historical
compositions are preserved for tracking changes over time.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime

from data_sources.b3.index.catalog import (
    INDEX_CATALOG, ACTIVE_INDICES, connect, ensure_schema,
)
from data_sources.b3.index.fetcher import fetch_index, fetch_indices_concurrent


def sync_index(index_code: str, force: bool = False, verbose: bool = True) -> dict:
    """Sync a single B3 index composition.

    Args:
        index_code: B3 index code (IBOV, SMLL, etc).
        force: Bypass cache.
        verbose: Print progress.

    Returns:
        Dict with sync status, index code, constituent count.
    """
    def _log(msg: str) -> None:
        if verbose:
            print(f"[b3.index] {msg}", file=sys.stderr, flush=True)

    name = INDEX_CATALOG.get(index_code, ("unknown", "", False))[0]
    _log(f"Syncing {index_code} ({name})...")

    result = fetch_index(index_code, force=force)
    if result.get("status") != "ok":
        return result

    constituents = result.get("constituents", [])
    if not constituents:
        return {"status": "not_found", "index": index_code, "error": "No constituents returned"}

    ref_date = result.get("ref_date", "")
    if not ref_date:
        ref_date = datetime.now().strftime("%Y-%m-%d")

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        synced_at = result.get("synced_at", datetime.now().isoformat())

        for c in constituents:
            conn.execute(
                """INSERT OR REPLACE INTO index_constituents
                   (index_code, ticker, company_name, type, theorical_qty,
                    participation, rank, ref_date, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (index_code, c["ticker"], c["company_name"], c["type"],
                 c.get("theorical_qty"), c.get("participation"),
                 c.get("rank"), ref_date, synced_at),
            )

        conn.execute(
            """INSERT OR REPLACE INTO sync_state
               (index_code, last_date, synced_at, row_count)
               VALUES (?, ?, ?, ?)""",
            (index_code, ref_date, synced_at, len(constituents)),
        )
        conn.commit()

        _log(f"  stored {len(constituents)} constituents (ref: {ref_date})")

        return {
            "status": "ok",
            "index": index_code,
            "name": name,
            "constituents_stored": len(constituents),
            "ref_date": ref_date,
            "synced_at": synced_at,
        }
    except Exception as e:
        return {"status": "error", "index": index_code, "error": str(e)}
    finally:
        conn.close()


def sync_all(force: bool = False, verbose: bool = True) -> dict:
    """Sync ALL active indices concurrently.

    Args:
        force: Bypass cache.
        verbose: Print progress.

    Returns:
        Dict with per-index results + summary.
    """
    def _log(msg: str) -> None:
        if verbose:
            print(f"[b3.index] {msg}", file=sys.stderr, flush=True)

    codes = ACTIVE_INDICES
    _log(f"Syncing {len(codes)} active indices: {codes}")
    sync_start = time.time()

    results = fetch_indices_concurrent(codes, force=force)

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        synced_at = datetime.now().isoformat()
        summary = {"synced": [], "errors": []}
        total_rows = 0

        for code, result in results.items():
            name = INDEX_CATALOG.get(code, ("unknown", "", False))[0]
            if result.get("status") != "ok":
                _log(f"  {code} ({name}): FAILED - {result.get('error', '')}")
                summary["errors"].append({"index": code, "name": name, "error": result.get("error", "")})
                continue

            constituents = result.get("constituents", [])
            ref_date = result.get("ref_date", "")
            if not ref_date:
                ref_date = datetime.now().strftime("%Y-%m-%d")
            row_synced_at = result.get("synced_at", synced_at)

            for c in constituents:
                conn.execute(
                    """INSERT OR REPLACE INTO index_constituents
                       (index_code, ticker, company_name, type, theorical_qty,
                        participation, rank, ref_date, synced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (code, c["ticker"], c["company_name"], c["type"],
                     c.get("theorical_qty"), c.get("participation"),
                     c.get("rank"), ref_date, row_synced_at),
                )

            conn.execute(
                """INSERT OR REPLACE INTO sync_state
                   (index_code, last_date, synced_at, row_count)
                   VALUES (?, ?, ?, ?)""",
                (code, ref_date, row_synced_at, len(constituents)),
            )

            total_rows += len(constituents)
            summary["synced"].append({"index": code, "name": name, "constituents": len(constituents), "ref_date": ref_date})
            _log(f"  {code} ({name}): {len(constituents)} constituents (ref: {ref_date})")

        conn.commit()
        elapsed = time.time() - sync_start
        _log(f"Done in {elapsed:.1f}s - {total_rows} total constituents, {len(summary['errors'])} errors")

        return {
            "status": "ok" if not summary["errors"] else "partial",
            "indices_synced": len(summary["synced"]),
            "indices_failed": len(summary["errors"]),
            "total_constituents": total_rows,
            "elapsed_s": round(elapsed, 1),
            **summary,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()
