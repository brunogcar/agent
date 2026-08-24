"""data_sources/b3/api/sync_engine.py -- Sync B3 data via CSV bulk download.

[v2.0] COMPLETE REWRITE — replaced the paginated JSON API (2,283 requests,
20 rows/page, 4 columns, 22-minute sync with server-side throttling) with
a 2-step CSV bulk download (1 request, ALL rows, ALL columns, ~1-3s).

The 2-step flow:
  Step 1: GET /api/download/requestname?fileName={table}&date={date}
    → JSON: {"token": "...", "file": {"name": "...", "extension": ".csv"}}

  Step 2: GET /api/download/?token={token}
    → Full CSV file (semicolon-separated, 17-52 columns, 633-169K rows)

CRITICAL: The download URL is /api/download/ (with trailing slash). Without
the trailing slash, B3 returns an HTML consent page instead of the CSV.

CSV format:
  - Semicolon-separated (;)
  - ISO-8859-1 encoding (has Portuguese accents)
  - 3 of 4 tables have a "Status do Arquivo: Final" line before the header
    (derivatives does NOT — its first line IS the header)
  - No quoting/escaping needed (B3 doesn't embed semicolons in values)

Performance comparison (derivatives, 2026-08-21):
  Old (JSON pagination): 2,283 requests, 13,980 rows, 4 columns, 1,331s
  New (CSV bulk):        1 request,     45,653 rows, 17 columns, 0.9s
  Speedup:               1,477x faster, 3.3x more rows, 4.25x more columns

FUTURE: B3 announced the BDI portal (https://arquivos.b3.com.br/bdi/tabelas)
as the replacement for the public data pages, with the "Quadro Analítico das
Posições em Aberto" expected from 2026-06-30. If the /api/download endpoint
is decommissioned, investigate the BDI portal as the replacement.
(Discovered by ChatGPT during the 2026-08-24 code review.)
"""

from __future__ import annotations

import csv
import io
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from core.tracer import tracer
from data_sources.b3.api.catalog import (
    DOWNLOAD_TOKEN_URL, DOWNLOAD_CSV_URL,
    B3_TABLES, db_path, connect, ensure_schema,
)

# Browser-like headers (B3's WAF rejects bare bot UAs with HTTP 400).
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://arquivos.b3.com.br",
    "Referer": "https://arquivos.b3.com.br/",
}

# CSV encoding: B3 uses ISO-8859-1 (Latin-1) for Portuguese accents.
_CSV_ENCODING = "iso-8859-1"


def _progress(msg: str) -> None:
    """Print progress to stderr (flushed)."""
    print(msg, file=sys.stderr, flush=True)


def sync(
    table: str = "instruments",
    date_str: str = "",
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download B3 data via the CSV bulk download API.

    Args:
        table: instruments, trades, after_hours, derivatives. Default: instruments.
        date_str: YYYY-MM-DD. Default: today (falls back up to 7 days).
        force: Re-download even if sync_state says complete.
        trace_id: Tracer ID.

    Returns:
        Dict with sync status, row count, column count, elapsed time.
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

        # ── Resume check: is this date already synced? ────────────────────
        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE table_name=? AND date=?",
                (table, date_str),
            ).fetchone()
            if existing and existing["row_count"] > 0:
                _progress(f"[b3_sync] {table} for {date_str} already synced ({existing['row_count']:,} rows) — skipping (use force=True to re-download)")
                return {
                    "status": "skipped",
                    "table": table, "date": date_str,
                    "rows": existing["row_count"],
                    "synced_at": existing["synced_at"],
                }

        # ── Step 1: Get the download token ────────────────────────────────
        # B3 publishes trade data with a delay — today's data is usually
        # not available until the next business day. Try up to 7 days back.
        token = None
        actual_date = date_str

        while True:
            token = _get_download_token(api_name, actual_date)
            if token:
                break

            if _user_specified_date:
                # User specified a date — don't fall back.
                return {"status": "no_data", "table": table, "date": actual_date,
                        "error": f"B3 API returned no data for {actual_date}. "
                                 f"Market may be closed or data not yet published."}

            # Try yesterday, etc.
            dt = datetime.strptime(actual_date, "%Y-%m-%d") - timedelta(days=1)
            actual_date = dt.strftime("%Y-%m-%d")
            _progress(f"[b3_sync] No data for {date_str}, trying {actual_date}")
            if actual_date < (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"):
                return {"status": "no_data", "table": table, "date": date_str,
                        "error": "No data from B3 API for any date tried (today + 7 days back)."}

        # ── Step 2: Download the CSV ───────────────────────────────────────
        _progress(f"[b3_sync] Downloading CSV for {actual_date}...")
        t0 = time.time()
        csv_text = _download_csv(token)
        elapsed_download = time.time() - t0

        if not csv_text:
            return {"status": "error", "table": table, "date": actual_date,
                    "error": "CSV download returned empty response."}

        # ── Parse the CSV ──────────────────────────────────────────────────
        columns, rows, file_status = _parse_csv(csv_text)

        if not columns:
            return {"status": "error", "table": table, "date": actual_date,
                    "error": "CSV has no column header."}

        # [v3 fix] Skip partial data — keep previous full sync.
        # B3 marks intraday snapshots as "Parcial" and end-of-day as "Final".
        # If we sync partial data, we lose the complete previous day's data
        # (the DELETE wipes it, then the INSERT puts partial data in).
        if file_status == "Parcial":
            _progress(f"[b3_sync] Skipping {table} for {actual_date} — data is Parcial (market hours). Previous full sync preserved.")
            # Check if we already have data for this date from a previous Final sync
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE table_name=? AND date=?",
                (table, actual_date),
            ).fetchone()
            if existing and existing["row_count"] > 0:
                return {
                    "status": "skipped_partial",
                    "table": table, "date": actual_date,
                    "rows": existing["row_count"],
                    "synced_at": existing["synced_at"],
                    "message": "Data is Parcial — keeping previous Final sync.",
                }
            # No previous data — try yesterday
            if not _user_specified_date:
                dt = datetime.strptime(actual_date, "%Y-%m-%d") - timedelta(days=1)
                prev_date = dt.strftime("%Y-%m-%d")
                _progress(f"[b3_sync] No previous Final sync for {actual_date}, trying {prev_date}")
                token = _get_download_token(api_name, prev_date)
                if token:
                    csv_text = _download_csv(token)
                    if csv_text:
                        columns, rows, file_status = _parse_csv(csv_text)
                        if file_status == "Parcial":
                            _progress(f"[b3_sync] {prev_date} is also Parcial — skipping")
                            return {"status": "skipped_partial", "table": table,
                                    "date": actual_date, "rows": 0,
                                    "message": "No Final data available."}
                        actual_date = prev_date
                if not columns:
                    return {"status": "no_data", "table": table, "date": actual_date,
                            "error": "No Final data found."}
            else:
                return {"status": "skipped_partial", "table": table,
                        "date": actual_date, "rows": 0,
                        "message": "Data is Parcial — use force=True after market close."}

        _progress(f"[b3_sync] CSV parsed: {len(rows):,} rows, {len(columns)} columns, status={file_status or 'N/A'} ({elapsed_download:.1f}s download)")

        # ── Create/update schema + insert all rows ────────────────────────
        # [v2 fix] ensure_schema now handles schema migration (adds missing
        # columns via ALTER TABLE ADD COLUMN). This fixes the "no such column"
        # error when upgrading from the old 4-column JSON API schema.
        ensure_schema(conn, table, columns)
        db_table = B3_TABLES[table]["table"]

        # Delete old data for this date (full refresh).
        # [v2 fix] Commit the DELETE before the INSERT to avoid "cannot start
        # a transaction within a transaction" — sqlite3 Python opens an
        # implicit transaction on the DELETE, and conn.execute("BEGIN")
        # would conflict with it. Instead, just do DELETE + INSERT + COMMIT.
        date_col = "RptDt" if "RptDt" in columns else columns[0]
        conn.execute(f"DELETE FROM {db_table} WHERE {date_col} LIKE ?", (f"%{actual_date}%",))
        conn.commit()  # close the DELETE transaction

        # Bulk insert in a single transaction.
        col_str = ", ".join(columns) + ", _ingested_at"
        placeholders = ", ".join(["?"] * (len(columns) + 1))
        insert_sql = f"INSERT INTO {db_table} ({col_str}) VALUES ({placeholders})"

        now = datetime.now().isoformat()
        n_cols = len(columns)
        batch = []
        for row in rows:
            # Pad/truncate to match column count
            vals = list(row) + [""] * (n_cols - len(row))
            vals = vals[:n_cols] + [now]
            batch.append(tuple(vals))

        t_insert = time.time()
        conn.executemany(insert_sql, batch)
        conn.commit()
        elapsed_insert = time.time() - t_insert

        total_rows = len(batch)

        # ── Record sync state ──────────────────────────────────────────────
        synced_at = datetime.now().isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO sync_state "
            "(table_name, date, synced_at, row_count, page_count, last_page) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (table, actual_date, synced_at, total_rows, 1, 1),
        )
        conn.commit()

        elapsed_total = time.time() - t0
        _progress(f"[b3_sync] Done: {total_rows:,} rows in {elapsed_total:.1f}s "
                  f"(download {elapsed_download:.1f}s + insert {elapsed_insert:.1f}s)")

        return {
            "status": "ok",
            "table": table,
            "date": actual_date,
            "rows": total_rows,
            "columns": len(columns),
            "synced_at": synced_at,
            "elapsed_s": round(elapsed_total, 1),
            "download_s": round(elapsed_download, 1),
            "insert_s": round(elapsed_insert, 1),
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


def _get_download_token(api_name: str, date_str: str) -> str | None:
    """Step 1: Request a download token from B3.

    [v3 fix] Added retry with backoff (3 attempts). (Claude 2 review finding.)
    """
    for attempt in range(3):
        try:
            resp = httpx.get(
                DOWNLOAD_TOKEN_URL,
                params={"fileName": api_name, "date": date_str},
                headers=_HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                token = resp.json().get("token", "")
                if token:
                    return token
                return None  # 200 but no token = not yet published
            if resp.status_code == 400:
                return None  # No data for this date
            # 5xx or other — retry
        except Exception:
            pass
        if attempt < 2:
            time.sleep(1 * (attempt + 1))  # 1s, 2s backoff
    return None


def _download_csv(token: str) -> str:
    """Step 2: Download the CSV file using the token.

    CRITICAL: The URL is /api/download/ (with trailing slash). Without it,
    B3 returns an HTML consent page instead of the CSV.

    [v3 fix] Added retry with backoff (3 attempts). If the token expires
    mid-download (possible for the ~37MB instruments file), the caller
    re-requests a fresh token. (Claude 2 review finding.)
    """
    for attempt in range(3):
        try:
            resp = httpx.get(
                DOWNLOAD_CSV_URL,
                params={"token": token},
                headers=_HEADERS,
                timeout=300,  # 5 min for large files (instruments is ~37 MB)
                follow_redirects=True,
            )
            if resp.status_code == 200:
                return resp.content.decode(_CSV_ENCODING)
            # Non-200 — retry
        except Exception:
            pass
        if attempt < 2:
            time.sleep(2 * (attempt + 1))  # 2s, 4s backoff
    return ""


def _parse_csv(csv_text: str) -> tuple[list[str], list[list[str]], str]:
    """Parse the B3 CSV into (columns, rows, status).

    Handles the "Status do Arquivo: Final/Parcial" line that 3 of 4 tables
    have before the actual header. Derivatives does NOT have this line
    (its first line IS the header — status is assumed "Final").

    [v3 fix] Uses csv.reader instead of naive split(";") to handle
    potential semicolons inside quoted fields (e.g. company names in
    the 52-column instruments table). (Claude 1 review finding.)

    Returns:
        (column_names, data_rows, status) where:
        - column_names: list of str
        - data_rows: list of list[str]
        - status: "Final" | "Parcial" | "" (empty if no status line)
    """
    import io
    lines = csv_text.strip().split("\n")
    if not lines:
        return [], [], ""

    # Detect if line 0 is the "Status do Arquivo" line or the header.
    status = ""
    header_idx = 0
    if "Status do Arquivo" in lines[0]:
        # Parse the status: "Status do Arquivo: Final" or "... Parcial"
        status = lines[0].split(":")[-1].strip() if ":" in lines[0] else ""
        header_idx = 1

    if header_idx >= len(lines):
        return [], [], status

    # [v3 fix] Use csv.reader for proper quoting/escaping handling.
    reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])), delimiter=";")
    rows_raw = list(reader)
    if not rows_raw:
        return [], [], status

    columns = [c.strip() for c in rows_raw[0]]
    rows = [r for r in rows_raw[1:] if r and any(v.strip() for v in r)]

    return columns, rows, status
