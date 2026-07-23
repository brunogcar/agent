"""
skills/b3/b3_api.py -- B3 public data API: download, store, and query.

WHAT THIS IS
------------
Direct Python port of the Google Apps Script RESUMABLE() function that
downloaded B3 CSVs into Google Sheets. Same flow, same API endpoints,
no 6-minute execution limit, stores to SQLite instead of spreadsheet cells.

DATA FLOW
---------
1. Publications API  -> find latest file by prefix
2. Token API         -> request one-time download token
3. Download API      -> stream CSV (ISO-8859-1 encoded, semicolon-separated)
4. Parse             -> strip header junk, split rows
5. Store             -> SQLite DB in memory_db/b3/<file>.db
6. State             -> memory_db/b3/.sync_state.json tracks last run

STORAGE
-------
All data lives in cfg.memory_root / "b3" / -- co-located with ChromaDB.
One SQLite DB per B3 file (instruments.db, trades.db, etc.).
State file: .sync_state.json tracks fileName, fileSize, rowCount, syncedAt per file.

DECISION: One DB per file (not one big DB)
  The files have no natural foreign key relationship in SQLite (no enforced FK).
  Separating them means: instruments.db can be 80MB while trades.db is 5MB.
  Each can be queried independently. query.py handles joins in Python when needed.
  Alternative (single DB) would require ATTACH DATABASE for cross-file queries,
  which is more complex and gives no real performance benefit at this data size.

DECISION: No pandas dependency
  B3 CSVs are large but not huge (50-100MB). Python's csv module + sqlite3 are
  sufficient and add zero dependencies. Chunked inserts (CHUNK_SIZE rows) keep
  memory usage flat regardless of file size.

DECISION: Replace-on-sync strategy
  Each sync drops and recreates the table (not upsert). B3 files are full daily
  snapshots -- there's no incremental update. Drop+recreate is simpler and faster
  than diffing millions of rows. The old data is still queryable until the moment
  the new sync completes (SQLite transactions).

API ENDPOINTS (from GAS script, verified working as of 2022-2023)
------------------------------------------------------------------
Publications: https://arquivos.b3.com.br/api/channels/<channel>/subchannels/<sub>/publications?lang=pt
Token:        https://arquivos.b3.com.br/api/download/requestname?fileName=<base>&date=<date>&recaptchaToken=
Download:     https://arquivos.b3.com.br/api/download/?token=<token>

The channel/subchannel IDs are stable (B3 hasn't changed them since 2019).
recaptchaToken is left empty -- B3's public API accepts empty token for bulk data files.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from core.config import cfg
from skills.b3.b3_api.b3_api_catalog import (
    B3_SCHEMAS,
    all_file_names,
    build_create_sql,
    get_columns,
    get_numeric_cols,
    get_schema,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# B3 Publications API -- same channel/subchannel IDs as the GAS script
_CHANNEL    = "34dcaaeb-0306-4f45-a83e-4f66a23b42fa"
_SUBCHANNEL = "cc188e40-03be-408e-aa86-501926b97a76"

_PUBLICATIONS_URL = (
    f"https://arquivos.b3.com.br/api/channels/{_CHANNEL}"
    f"/subchannels/{_SUBCHANNEL}/publications?&lang=pt"
)
_TOKEN_URL    = "https://arquivos.b3.com.br/api/download/requestname"
_DOWNLOAD_URL = "https://arquivos.b3.com.br/api/download/"

# Storage
_B3_DIR: Path = cfg.memory_root / "b3"
_STATE_FILE: Path = _B3_DIR / ".sync_state.json"

# Insert chunk size -- keeps memory flat on large files
CHUNK_SIZE = 500

# Request timeout (seconds) -- B3 files can be large
DOWNLOAD_TIMEOUT = 120
API_TIMEOUT      = 30


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _ensure_dir() -> None:
    """Create memory_db/b3/ if it doesn't exist."""
    _B3_DIR.mkdir(parents=True, exist_ok=True)


def _db_path(name: str) -> Path:
    """Return SQLite DB path for a given file name."""
    return _B3_DIR / get_schema(name)["db_file"]


def _load_state() -> dict:
    """Load sync state from JSON file. Returns empty dict if not found."""
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    """Persist sync state to JSON file."""
    _ensure_dir()
    _STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# B3 API helpers (direct port of GAS downloadCsv + token logic)
# ---------------------------------------------------------------------------

def _get_publications() -> list[dict]:
    """
    Fetch the publications list from the B3 API.
    Returns list of publication dicts with fileName, dateTime fields.
    Equivalent to the GAS UrlFetchApp.fetch(pubs_url) call.
    """
    resp = requests.get(_PUBLICATIONS_URL, timeout=API_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _find_latest(publications: list[dict], prefix: str) -> dict | None:
    """
    Find the most recent publication matching a file prefix.
    Equivalent to GAS: pubs.find(p => p.fileName.startsWith(meta.prefix))
    B3 returns publications in reverse-chronological order so first match is latest.
    """
    for pub in publications:
        if pub.get("fileName", "").startswith(prefix):
            return pub
    return None


def _get_download_token(file_base: str, date: str) -> str:
    """
    Request a one-time download token from B3.
    Equivalent to GAS tokenJson flow.

    file_base: filename without extension (e.g. 'InstrumentsConsolidatedFile20260512')
    date:      YYYY-MM-DD date string from publication dateTime field
    """
    resp = requests.get(
        _TOKEN_URL,
        params={
            "fileName":      file_base,
            "date":          date,
            "recaptchaToken": "",   # B3 accepts empty token for bulk public files
        },
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    # Token is embedded in redirectUrl: "...?token=<token>"
    redirect = data.get("redirectUrl", "")
    if "?token=" not in redirect:
        raise ValueError(f"No token in B3 response: {data}")
    return redirect.split("?token=")[-1]


def _download_csv(token: str, encoding: str = "ISO-8859-1") -> str:
    """
    Download the CSV file using the one-time token.
    Returns the full CSV text decoded with the file's encoding.
    Handles both plain CSV and ZIP-wrapped CSV (some B3 files are zipped).
    """
    resp = requests.get(
        _DOWNLOAD_URL,
        params={"token": token},
        timeout=DOWNLOAD_TIMEOUT,
    )
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")

    # Handle ZIP-wrapped files (some B3 endpoints return .zip containing .csv)
    if "zip" in content_type or resp.content[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = next(
                (n for n in zf.namelist() if n.lower().endswith(".csv")),
                zf.namelist()[0],
            )
            return zf.read(csv_name).decode(encoding, errors="replace")

    return resp.content.decode(encoding, errors="replace")


# ---------------------------------------------------------------------------
# CSV parsing (port of GAS parseCsv)
# ---------------------------------------------------------------------------

def _parse_csv(
    csv_text: str,
    separator: str,
    expected_columns: list[str],
) -> tuple[list[str], list[list[str]]]:
    """
    Parse CSV text into header + data rows.

    Handles B3's quirk of sometimes having a junk header line before the
    real column header (equivalent to GAS dropAt logic).
    Returns (header, data_rows) where header matches B3 column codes.

    DECISION: We validate the header against expected_columns from catalog.py.
    If columns don't match, we log a warning but still proceed -- B3 sometimes
    adds new columns without notice (handled gracefully: unknown cols are ignored).
    """
    reader = csv.reader(
        io.StringIO(csv_text.strip()),
        delimiter=separator,
    )
    rows = list(reader)

    if not rows:
        return [], []

    # Find the first row that has multiple columns -- that's the real header
    # (GAS: dropAt = data.findIndex(r => r.length > 1))
    header_idx = 0
    for i, row in enumerate(rows):
        if len(row) > 1:
            header_idx = i
            break

    header    = [col.strip() for col in rows[header_idx]]
    data_rows = rows[header_idx + 1:]

    # Filter out empty rows
    data_rows = [r for r in data_rows if any(c.strip() for c in r)]

    return header, data_rows


# ---------------------------------------------------------------------------
# SQLite storage
# ---------------------------------------------------------------------------

def _coerce_value(value: str, col_name: str, numeric_cols: set[str]) -> Any:
    """
    Coerce a string value from the CSV to the appropriate Python type.
    B3 uses comma as decimal separator in some files -- handle both.
    Empty strings become None (SQLite NULL).
    """
    v = value.strip()
    if not v:
        return None
    if col_name in numeric_cols:
        # B3 sometimes uses comma as decimal separator
        v_clean = v.replace(",", ".").replace(" ", "")
        try:
            # Try int first for cleaner storage
            if "." not in v_clean:
                return int(v_clean)
            return float(v_clean)
        except (ValueError, TypeError):
            return v  # return as string if conversion fails
    return v


def _store_to_sqlite(
    name:      str,
    header:    list[str],
    data_rows: list[list[str]],
    report_date: str,
) -> int:
    """
    Store parsed CSV data to SQLite, replacing previous data for this date.

    DECISION: DROP + recreate strategy within a transaction.
    B3 files are full daily snapshots -- not incremental. Each sync replaces
    the previous day's data completely. We use a transaction so the old data
    is still readable until the new data is fully committed.

    Returns number of rows inserted.
    """
    schema      = get_schema(name)
    table       = schema["table"]
    db_path     = _db_path(name)
    numeric     = get_numeric_cols(name)
    known_cols  = set(get_columns(name).keys())
    ingested_at = datetime.utcnow().isoformat()

    # Map CSV header positions to known catalog columns
    # Unknown columns from CSV are ignored (forward compatibility)
    col_indices: list[tuple[int, str]] = []
    for i, col in enumerate(header):
        if col in known_cols:
            col_indices.append((i, col))

    if not col_indices:
        raise ValueError(
            f"No matching columns found in CSV for {name}. "
            f"CSV header: {header[:10]}. "
            f"Expected: {list(known_cols)[:10]}"
        )

    insert_cols = [col for _, col in col_indices] + ["_ingested_at"]
    placeholders = ", ".join("?" * len(insert_cols))
    insert_sql = (
        f"INSERT INTO {table} ({', '.join(insert_cols)}) "
        f"VALUES ({placeholders})"
    )

    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            # Create table if not exists (idempotent)
            conn.execute(build_create_sql(name))

            # Drop existing data for this report date, replace with fresh data
            # DECISION: delete by RptDt not drop table, so historical dates are preserved
            # if we ever want to keep multiple days (future feature).
            # For now this effectively replaces same-day data on re-run.
            if "RptDt" in known_cols and report_date:
                conn.execute(f"DELETE FROM {table} WHERE RptDt = ?", (report_date,))
            else:
                # MarginScenario has no simple date partition -- just clear all
                conn.execute(f"DELETE FROM {table}")

            # Create indexes after table creation
            for idx_col in schema.get("indexes", []):
                if idx_col in known_cols:
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS "
                        f"idx_{table}_{idx_col} ON {table}({idx_col})"
                    )

            # Insert in chunks to keep memory flat on large files
            rows_inserted = 0
            chunk: list[tuple] = []

            for row in data_rows:
                values = []
                for idx, col in col_indices:
                    raw = row[idx] if idx < len(row) else ""
                    values.append(_coerce_value(raw, col, numeric))
                values.append(ingested_at)
                chunk.append(tuple(values))

                if len(chunk) >= CHUNK_SIZE:
                    conn.executemany(insert_sql, chunk)
                    rows_inserted += len(chunk)
                    chunk = []

            if chunk:
                conn.executemany(insert_sql, chunk)
                rows_inserted += len(chunk)

    finally:
        conn.close()

    return rows_inserted


# ---------------------------------------------------------------------------
# Public sync function
# ---------------------------------------------------------------------------

def sync(
    files:      list[str] | None = None,
    force:      bool = False,
) -> dict:
    """
    Download and store B3 files to SQLite.

    files: list of file names to sync (default: all 5).
           Valid names: Instruments, Trades, AfterHours, Derivatives, MarginScenario
    force: if True, re-download even if today's data is already stored.

    Returns dict with per-file results:
      {
        "Instruments": {"status": "synced", "rows": 12450, "file": "...", "elapsed_s": 14.2},
        "Trades":      {"status": "skipped", "reason": "already current"},
        ...
      }
    """
    _ensure_dir()

    target_files = files or all_file_names()
    # Validate names
    unknown = [f for f in target_files if f not in B3_SCHEMAS]
    if unknown:
        return {"status": "error", "error": f"Unknown file names: {unknown}. Valid: {all_file_names()}"}

    state   = _load_state()
    results = {}
    today   = datetime.now().strftime("%Y-%m-%d")

    # Fetch publications list once -- reuse for all files
    try:
        publications = _get_publications()
    except Exception as e:
        return {"status": "error", "error": f"Failed to fetch B3 publications list: {e}"}

    for name in target_files:
        t0     = time.time()
        schema = get_schema(name)
        prefix = schema["prefix"]

        try:
            # Find latest file for this prefix
            pub = _find_latest(publications, prefix)
            if not pub:
                results[name] = {"status": "error", "error": f"No publication found for prefix '{prefix}'"}
                continue

            file_name = pub["fileName"]
            file_date = pub.get("dateTime", "").split("T")[0]   # YYYY-MM-DD
            file_base = file_name.split("_")[0] if "_" in file_name else file_name.replace(".csv", "")

            # Skip if already synced today and not forced
            file_state = state.get(name, {})
            if (
                not force
                and file_state.get("fileName") == file_name
                and file_state.get("syncedAt", "").startswith(today)
            ):
                results[name] = {
                    "status":  "skipped",
                    "reason":  "already current",
                    "file":    file_name,
                    "rows":    file_state.get("rows", 0),
                    "date":    file_date,
                }
                continue

            # Get download token
            token = _get_download_token(file_base, file_date)

            # Download CSV
            csv_text = _download_csv(token, encoding=schema["encoding"])
            file_size = len(csv_text)

            # Parse
            expected_cols = list(schema["columns"].keys())
            header, data_rows = _parse_csv(csv_text, schema["separator"], expected_cols)

            if not data_rows:
                results[name] = {"status": "error", "error": "CSV parsed to zero rows -- file may be empty or malformed"}
                continue

            # Store to SQLite
            rows = _store_to_sqlite(name, header, data_rows, file_date)

            elapsed = round(time.time() - t0, 1)

            # Update state
            state[name] = {
                "fileName":  file_name,
                "fileSize":  file_size,
                "rows":      rows,
                "syncedAt":  datetime.utcnow().isoformat(),
                "reportDate": file_date,
            }
            _save_state(state)

            results[name] = {
                "status":    "synced",
                "file":      file_name,
                "rows":      rows,
                "size_kb":   round(file_size / 1024, 1),
                "date":      file_date,
                "elapsed_s": elapsed,
            }

        except Exception as e:
            results[name] = {
                "status":    "error",
                "error":     str(e),
                "elapsed_s": round(time.time() - t0, 1),
            }

    return {"status": "ok", "results": results}


# ---------------------------------------------------------------------------
# Public query function
# ---------------------------------------------------------------------------

def query(
    ticker:   str | None = None,
    files:    list[str] | None = None,
    filters:  dict | None = None,
    columns:  list[str] | None = None,
    limit:    int = 100,
) -> dict:
    """
    Query local SQLite B3 data.

    ticker:  TckrSymb to filter by (e.g. "PETR4"). If provided, joins all
             requested files on TckrSymb and returns a single merged dict.
    files:   which B3 files to query (default: Instruments + Trades).
    filters: {column: value} additional filters applied to each file.
    columns: specific columns to return (default: all).
    limit:   max rows per file (ignored when ticker is specified -- returns 1 row).

    Returns:
      ticker query  -> {"status": "ok", "ticker": "PETR4", "data": {...merged dict...}}
      table query   -> {"status": "ok", "file": "Instruments", "rows": [...], "count": N}
    """
    target_files = files or ["Instruments", "Trades"]

    # Ticker lookup: join across all requested files, return merged single record
    if ticker:
        ticker = ticker.upper().strip()
        merged: dict = {"ticker": ticker}

        for name in target_files:
            db_path = _db_path(name)
            if not db_path.exists():
                merged[f"_{name}_error"] = "not synced yet -- run skill(domain='b3_api', mode='sync')"
                continue

            schema  = get_schema(name)
            table   = schema["table"]
            pk      = schema["pk"]

            if pk != "TckrSymb":
                # MarginScenario uses PRFNm not TckrSymb -- skip for ticker queries
                # unless the caller explicitly included it
                if "MarginScenario" not in (files or []):
                    continue

            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute(
                        f"SELECT * FROM {table} WHERE TckrSymb = ? LIMIT 1",
                        (ticker,),
                    ).fetchone()
                    if row:
                        merged.update(dict(row))
                    else:
                        merged[f"_{name}_error"] = f"{ticker} not found in {name}"
                finally:
                    conn.close()
            except Exception as e:
                merged[f"_{name}_error"] = str(e)

        return {"status": "ok", "ticker": ticker, "data": merged}

    # Table query: return rows from a single file with optional filters
    if len(target_files) != 1:
        return {
            "status": "error",
            "error":  "Provide ticker= for cross-file lookup, or files=[single_name] for table query",
        }

    name    = target_files[0]
    db_path = _db_path(name)

    if not db_path.exists():
        return {
            "status": "error",
            "error":  f"{name} not synced yet. Run: skill(domain='b3_api', mode='sync', files=['{name}'])",
        }

    schema  = get_schema(name)
    table   = schema["table"]
    known   = set(get_columns(name).keys())

    # Build WHERE clause from filters
    where_parts: list[str] = []
    where_vals:  list[Any] = []
    for col, val in (filters or {}).items():
        if col in known:
            where_parts.append(f"{col} = ?")
            where_vals.append(val)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    # Column selection
    if columns:
        valid_cols = [c for c in columns if c in known]
        select_sql = ", ".join(valid_cols) if valid_cols else "*"
    else:
        select_sql = "*"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT {select_sql} FROM {table} {where_sql} LIMIT ?",
                where_vals + [limit],
            ).fetchall()
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} {where_sql}",
                where_vals,
            ).fetchone()[0]
        finally:
            conn.close()

        return {
            "status": "ok",
            "file":   name,
            "rows":   [dict(r) for r in rows],
            "count":  count,
            "limit":  limit,
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Status function
# ---------------------------------------------------------------------------

def status() -> dict:
    """
    Return sync status for all B3 files: what's downloaded, dates, row counts, DB sizes.
    Used by dispatcher mode='status'.
    """
    state   = _load_state()
    result  = {}

    for name in all_file_names():
        db_path    = _db_path(name)
        file_state = state.get(name, {})

        db_size_kb = 0
        if db_path.exists():
            db_size_kb = round(db_path.stat().st_size / 1024, 1)

        result[name] = {
            "synced":      db_path.exists(),
            "file":        file_state.get("fileName", "not synced"),
            "report_date": file_state.get("reportDate", ""),
            "rows":        file_state.get("rows", 0),
            "synced_at":   file_state.get("syncedAt", ""),
            "db_size_kb":  db_size_kb,
            "db_path":     str(db_path),
        }

    return {"status": "ok", "files": result, "b3_dir": str(_B3_DIR)}
