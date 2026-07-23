"""data_sources/b3/api/sync_engine.py -- Sync B3 data via paginated JSON API.

B3 migrated from the old 3-step CSV download to a paginated JSON API.
20 rows per page, no authentication needed.

[v1.0.4] Batch commit + resume: Commits every BATCH_SIZE pages (10K rows)
so a cancelled sync keeps what's been fetched. On restart, resumes from
the last committed page. Uses ThreadPoolExecutor(10 workers) for speed.

API: GET /tabelas/table/{tableName}/{date}/{page}
  -> {"name", "columns": [...], "values": [[...], ...], "pageCount": N}
"""

from __future__ import annotations

import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import httpx

from core.tracer import tracer
from data_sources.b3.api.catalog import (
    API_BASE, PAGE_SIZE, B3_TABLES, db_path, connect, ensure_schema,
)

MAX_WORKERS = 10
BATCH_SIZE = 500  # commit every 500 pages (10K rows)


def _progress(msg: str) -> None:
    """Print progress to stderr (flushed)."""
    print(msg, file=sys.stderr, flush=True)


def sync(
    table: str = "instruments",
    date_str: str = "",
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download B3 data via concurrent paginated JSON API with batch commit + resume.

    Args:
        table: instruments, trades, after_hours, derivatives. Default: instruments.
        date_str: YYYY-MM-DD. Default: today.
        force: Re-download from page 1 (ignores partial sync state).
        trace_id: Tracer ID.

    Returns:
        Dict with sync status, row count, page count, elapsed time.
    """
    tid = trace_id or ""

    if table not in B3_TABLES:
        return {"status": "error",
                "error": f"Unknown table '{table}'. Available: {list(B3_TABLES.keys())}"}

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        _user_specified_date = False
    else:
        _user_specified_date = True

    api_name = B3_TABLES[table]["api_name"]
    _progress(f"[b3_sync] Syncing {table} ({api_name}) for {date_str}")

    conn = connect(table, read_only=False)
    try:
        _ensure_sync_state_table(conn)

        # ── Resume check: do we have a partial sync for this date? ─────────
        resume_from = 1
        if not force:
            partial = conn.execute(
                "SELECT * FROM sync_state WHERE table_name=? AND date=?",
                (table, date_str),
            ).fetchone()
            if partial:
                # [v1.0.4 fix] Check if sync is COMPLETE (last_page == page_count)
                # vs PARTIAL (last_page < page_count). The old check used
                # row_count > 0 which treated any partial sync as complete.
                last_page = partial["last_page"] or 0
                total_pages = partial["page_count"] or 0
                if last_page > 0 and total_pages > 0 and last_page >= total_pages:
                    # Complete sync — skip
                    return {
                        "status": "skipped",
                        "table": table, "date": date_str,
                        "rows": partial["row_count"],
                        "pages": partial["page_count"],
                        "synced_at": partial["synced_at"],
                    }
                # Partial: resume from last_page + 1
                resume_from = last_page + 1
                if resume_from > 1:
                    _progress(f"[b3_sync] Resuming from page {resume_from:,} (partial sync: {last_page:,}/{total_pages:,} pages, {partial['row_count']:,} rows)")

        # ── Fetch page 1 to get column metadata + pageCount ─────────────────
        # [v1.0.4] Skip page 1 fetch on resume — we already have columns from the schema
        if resume_from > 1:
            # Resuming: get columns from existing table schema
            col_rows = conn.execute(f"PRAGMA table_info({B3_TABLES[table]['table']})").fetchall()
            columns = [r["name"] for r in col_rows if r["name"] != "_ingested_at"]
            page_count = total_pages  # from partial sync_state
            page1 = None  # don't re-process page 1
        else:
            page1 = _fetch_page(api_name, date_str, 1)
            if not page1:
                # Try yesterday if user didn't specify a date
                if not _user_specified_date:
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    _progress(f"[b3_sync] No data for today, trying {yesterday}")
                    date_str = yesterday
                    page1 = _fetch_page(api_name, date_str, 1)
                if not page1:
                    return {"status": "no_data", "table": table, "date": date_str,
                            "error": "No data from B3 API. Market may not have closed yet."}

            columns = [c["name"] for c in page1.get("columns", [])]
            if not columns:
                return {"status": "error", "table": table, "date": date_str,
                        "error": "No columns in B3 API response"}

            page_count = page1.get("pageCount", 0)

            if page_count == 0:
                return {"status": "no_data", "table": table, "date": date_str,
                        "error": f"B3 API returned 0 pages for {date_str}."}

        ensure_schema(conn, table, columns)
        db_table = B3_TABLES[table]["table"]
        date_col = "RptDt" if "RptDt" in columns else columns[0]
        col_str = ", ".join(columns) + ", _ingested_at"
        placeholders = ", ".join(["?"] * (len(columns) + 1))
        insert_sql = f"INSERT INTO {db_table} ({col_str}) VALUES ({placeholders})"

        # ── If starting fresh (page 1), delete old data + store page 1 ──────
        total_rows = 0
        if resume_from > 1:
            # Resuming: keep existing rows, start counting from partial count
            total_rows = partial["row_count"]
        elif page1:
            # Fresh start: delete old data, store page 1 values
            conn.execute(f"DELETE FROM {db_table} WHERE {date_col} LIKE ?", (f"%{date_str}%",))
            conn.commit()
            page1_values = page1.get("values", [])
            total_rows += _insert_rows(conn, insert_sql, columns, page1_values)
            _save_partial_state(conn, table, date_str, total_rows, page_count, 1)

        _progress(f"[b3_sync] {table}: {page_count:,} pages total, starting from page {resume_from:,}. Fetching with {MAX_WORKERS} workers...")

        # ── Fetch remaining pages in batches (concurrent + commit) ──────────
        t0 = time.time()
        pages_done = resume_from - 1  # already done before resume

        while resume_from <= page_count:
            # Calculate batch range
            batch_end = min(resume_from + BATCH_SIZE - 1, page_count)
            batch_pages = list(range(resume_from, batch_end + 1))

            # Fetch batch concurrently
            batch_results: dict[int, list] = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                future_to_page = {
                    pool.submit(_fetch_page, api_name, date_str, p): p
                    for p in batch_pages
                }
                for future in as_completed(future_to_page):
                    p = future_to_page[future]
                    try:
                        data = future.result()
                        if data and data.get("values"):
                            batch_results[p] = data["values"]
                    except Exception:
                        batch_results[p] = []

            # Insert batch in page order
            batch_rows = 0
            for p in sorted(batch_results.keys()):
                batch_rows += _insert_rows(conn, insert_sql, columns, batch_results[p])

            total_rows += batch_rows
            pages_done += len(batch_pages)

            # Commit batch + save partial state
            conn.commit()
            _save_partial_state(conn, table, date_str, total_rows, page_count, batch_end)

            # Progress
            elapsed = time.time() - t0
            rate = pages_done / elapsed if elapsed > 0 else 0
            eta = (page_count - pages_done) / rate if rate > 0 else 0
            _progress(f"[b3_sync] {pages_done:,}/{page_count:,} pages ({total_rows:,} rows) — {rate:.1f} p/s, ETA {eta:.0f}s — committed")

            resume_from = batch_end + 1

        elapsed_total = time.time() - t0
        _progress(f"[b3_sync] Done: {total_rows:,} rows in {elapsed_total:.0f}s")

        # ── Mark sync as complete ───────────────────────────────────────────
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (table_name, date, synced_at, row_count, page_count, last_page) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (table, date_str, now, total_rows, page_count, page_count),
        )
        conn.commit()

        return {
            "status": "ok",
            "table": table,
            "date": date_str,
            "rows": total_rows,
            "pages": page_count,
            "columns": len(columns),
            "synced_at": now,
            "elapsed_s": round(elapsed_total, 1),
        }

    except Exception as e:
        return {"status": "error", "table": table, "date": date_str, "error": str(e)}
    finally:
        conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_sync_state_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            table_name  TEXT,
            date        TEXT,
            synced_at   TEXT,
            row_count   INTEGER DEFAULT 0,
            page_count  INTEGER DEFAULT 0,
            last_page   INTEGER DEFAULT 0,
            PRIMARY KEY (table_name, date)
        )
    """)
    conn.commit()


def _save_partial_state(conn, table, date_str, row_count, page_count, last_page):
    """Save partial sync state so a cancelled sync can resume."""
    conn.execute(
        "INSERT OR REPLACE INTO sync_state (table_name, date, synced_at, row_count, page_count, last_page) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (table, date_str, datetime.now().isoformat(), row_count, page_count, last_page),
    )
    conn.commit()


def _insert_rows(conn, insert_sql, columns, values) -> int:
    """Insert a batch of rows. Returns count inserted."""
    if not values:
        return 0
    now = datetime.now().isoformat()
    batch = []
    for row in values:
        vals = list(row) + [""] * (len(columns) - len(row))
        vals = vals[:len(columns)] + [now]
        batch.append(tuple(vals))
    conn.executemany(insert_sql, batch)
    return len(batch)


def _fetch_page(api_name: str, date_str: str, page: int) -> dict | None:
    """Fetch a single page from the B3 JSON API (thread-safe via httpx)."""
    url = f"{API_BASE}/{api_name}/{date_str}/{page}"
    try:
        resp = httpx.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None
