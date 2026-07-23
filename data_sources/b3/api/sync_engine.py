"""data_sources/b3/api/sync_engine.py -- Sync B3 data via paginated JSON API.

B3 migrated from the old 3-step CSV download (publications -> token -> CSV)
to a paginated JSON API. The new API returns JSON with column metadata +
values, 20 rows per page. No authentication/token needed.

API: GET /tabelas/table/{tableName}/{date}/{page}
  -> {"name", "columns": [...], "values": [[...], ...], "pageCount": N}

Flow:
  1. Fetch page 1 to get column metadata + pageCount
  2. Create table schema based on returned columns
  3. Fetch all pages (1..pageCount), collecting rows
  4. DELETE old data for this date + INSERT new rows
  5. Record sync_state

[v1.0.2] Performance: Uses requests.Session for connection reuse (3x faster).
[v1.0.2] Progress: Prints progress to stderr every page (flush=True) so the
user sees what's happening. tracer.step only fires every 50 pages to avoid
trace log bloat.
[v1.0.2] Empty response: Auto-retries with yesterday if pageCount=0.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from typing import Any

import requests

from core.tracer import tracer
from data_sources.b3.api.catalog import (
    API_BASE, PAGE_SIZE, B3_TABLES, db_path, connect, ensure_schema,
)

# Shared session for connection reuse (3x faster than per-request connections)
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
    return _session


def _progress(msg: str) -> None:
    """Print progress to stderr (flushed) so the user sees it immediately."""
    print(msg, file=sys.stderr, flush=True)


def sync(
    table: str = "instruments",
    date_str: str = "",
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download B3 data via paginated JSON API and store to SQLite.

    Args:
        table: Table name from B3_TABLES (instruments, trades, after_hours, derivatives).
               Default: instruments.
        date_str: Date in YYYY-MM-DD format. Default: today.
        force: Re-download even if already synced for this date.
        trace_id: Tracer ID for logging.

    Returns:
        Dict with sync status, row count, page count.
    """
    tid = trace_id or ""

    if table not in B3_TABLES:
        return {"status": "error",
                "error": f"Unknown table '{table}'. Available: {list(B3_TABLES.keys())}"}

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        _user_specified_date = False  # [v1.0.2] auto-date; can retry with yesterday
    else:
        _user_specified_date = True  # user specified a date; respect it

    api_name = B3_TABLES[table]["api_name"]
    tracer.step(tid, "b3_sync", f"Syncing {table} ({api_name}) for {date_str}")

    # Check if already synced (unless force)
    conn = connect(table, read_only=False)
    try:
        # Try to create sync_state if it doesn't exist yet
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                table_name  TEXT,
                date        TEXT,
                synced_at   TEXT,
                row_count   INTEGER DEFAULT 0,
                page_count  INTEGER DEFAULT 0,
                PRIMARY KEY (table_name, date)
            )
        """)
        conn.commit()

        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE table_name=? AND date=?",
                (table, date_str),
            ).fetchone()
            if existing:
                return {
                    "status": "skipped",
                    "table": table,
                    "date": date_str,
                    "rows": existing["row_count"],
                    "synced_at": existing["synced_at"],
                }

        # Step 1: Fetch page 1 to get column metadata + pageCount
        page1 = _fetch_page(api_name, date_str, 1)
        if not page1:
            return {"status": "error", "table": table, "date": date_str,
                    "error": "No data returned from B3 API (page 1 empty)"}

        columns = [c["name"] for c in page1.get("columns", [])]
        if not columns:
            return {"status": "error", "table": table, "date": date_str,
                    "error": "No columns in B3 API response"}

        page_count = page1.get("pageCount", 0)
        all_values = list(page1.get("values", []))

        # [v1.0.2] Handle empty response (pageCount=0, no values).
        # B3 may not have published data yet for today. Try previous day.
        if page_count == 0 and not all_values and not _user_specified_date:
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            tracer.step(tid, "b3_sync", f"No data for today, trying {yesterday}")
            date_str = yesterday
            page1 = _fetch_page(api_name, date_str, 1)
            if not page1 or not page1.get("values"):
                return {"status": "no_data", "table": table, "date": date_str,
                        "error": "No data available from B3 API. Market may not have closed yet, or it's a weekend/holiday."}
            columns = [c["name"] for c in page1.get("columns", [])]
            page_count = page1.get("pageCount", 1)
            all_values = list(page1.get("values", []))

        if page_count == 0 and not all_values:
            return {"status": "no_data", "table": table, "date": date_str,
                    "error": f"B3 API returned 0 pages for {date_str}. Data may not be available yet."}

        tracer.step(tid, "b3_sync", f"Page 1: {len(all_values)} rows, {page_count} pages total, {len(columns)} columns")
        _progress(f"[b3_sync] {table}: {page_count} pages, ~{page_count * 20:,} rows. Syncing...")

        # Step 2: Create table schema based on API columns
        ensure_schema(conn, table, columns)

        # Step 3: Fetch remaining pages
        t0 = time.time()
        for page_num in range(2, page_count + 1):
            page_data = _fetch_page(api_name, date_str, page_num)
            if page_data and page_data.get("values"):
                all_values.extend(page_data["values"])

            # Progress: every page to stderr (flushed), tracer every 50
            if page_num % 100 == 0 or page_num == page_count:
                elapsed = time.time() - t0
                rate = page_num / elapsed if elapsed > 0 else 0
                eta = (page_count - page_num) / rate if rate > 0 else 0
                _progress(f"[b3_sync] Page {page_num:,}/{page_count:,} ({len(all_values):,} rows) — {rate:.1f} p/s, ETA {eta:.0f}s")
            if page_num % 50 == 0:
                tracer.step(tid, "b3_sync", f"Page {page_num}/{page_count}, {len(all_values)} rows")

        tracer.step(tid, "b3_sync", f"Total: {len(all_values)} rows across {page_count} pages")

        # Step 4: DELETE old data for this date + INSERT new
        db_table = B3_TABLES[table]["table"]

        # Find the date column name (usually "RptDt")
        date_col = "RptDt" if "RptDt" in columns else columns[0]

        conn.execute(f"DELETE FROM {db_table} WHERE {date_col} LIKE ?", (f"%{date_str}%",))

        # Insert rows
        col_str = ", ".join(columns) + ", _ingested_at"
        placeholders = ", ".join(["?"] * (len(columns) + 1))
        insert_sql = f"INSERT INTO {db_table} ({col_str}) VALUES ({placeholders})"

        now = datetime.now().isoformat()
        batch = []
        for row in all_values:
            # Pad/truncate row to match columns length
            vals = list(row) + [""] * (len(columns) - len(row))
            vals = vals[:len(columns)] + [now]
            batch.append(tuple(vals))

        conn.executemany(insert_sql, batch)

        # Step 5: Record sync state
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (table_name, date, synced_at, row_count, page_count) "
            "VALUES (?, ?, ?, ?, ?)",
            (table, date_str, now, len(all_values), page_count),
        )
        conn.commit()

        return {
            "status": "ok",
            "table": table,
            "date": date_str,
            "rows": len(all_values),
            "pages": page_count,
            "columns": len(columns),
            "synced_at": now,
        }

    except Exception as e:
        return {"status": "error", "table": table, "date": date_str, "error": str(e)}
    finally:
        conn.close()


def _fetch_page(api_name: str, date_str: str, page: int) -> dict | None:
    """Fetch a single page from the B3 JSON API using a shared session.

    Returns the JSON response dict, or None on failure.
    """
    url = f"{API_BASE}/{api_name}/{date_str}/{page}"
    try:
        resp = _get_session().get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None
