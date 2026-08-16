"""data_sources/b3/cotahist/sync_engine.py -- Download + parse COTAHIST ZIP files.

Downloads annual COTAHIST ZIP files from B3, parses the fixed-width text
format (streaming — line by line, not loading full 765MB into memory),
and stores to SQLite with batch commits.

Default: syncs 2010-present (matching CVM DFP start year).
Each year is ~87MB ZIP → ~765MB TXT → ~2-5 min download + parse + store.
"""

from __future__ import annotations

import io
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone

import httpx

from data_sources.b3.cotahist.catalog import (
    COTAHIST_URL, FIRST_YEAR, CSV_ENCODING,
    COTAHIST_LAYOUT, NUMERIC_COLS, INTEGER_COLS, BDI_FILTER,
    connect, ensure_schema,
)
# [v1.2] Derivatives support — options, term, forward stored in a separate table.
from data_sources.b3.cotahist_derivatives.catalog import (
    DERIVATIVES_BDI_FILTER, parse_option_ticker, BDI_TO_DERIVATIVE_TYPE,
    DERIVATIVES_SCHEMA_SQL as _DERIVATIVES_SCHEMA_SQL,
)
from data_sources.b3.cotahist_derivatives.catalog import ensure_schema as _ensure_deriv_schema

BATCH_SIZE = 50000  # commit every 50K rows (~1MB per batch)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ───────────────────────────────────────────────────────────────

def sync(
    year: int = 0,
    years: list[int] | None = None,
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download and store COTAHIST data for one or more years.

    Args:
        year: Single year (e.g., 2025). Ignored if `years` is given.
        years: List of years. Takes precedence over `year`.
               If neither given, syncs current year.
        force: Re-download even if already synced.
        trace_id: Tracer ID.

    Returns:
        For single year: the per-year result dict.
        For multiple years: {"status": "ok", "results": {year: result, ...}, ...}
    """
    # Determine which years to sync
    if years:
        targets = sorted(set(years))
    elif year:
        targets = [year]
    else:
        targets = [datetime.now().year]

    if len(targets) == 1:
        return _sync_year(targets[0], force=force)

    # Multiple years — aggregate
    results = {}
    synced = skipped = errors = 0
    for y in targets:
        r = _sync_year(y, force=force)
        results[y] = r
        st = r.get("status")
        if st == "ok":
            synced += 1
        elif st == "skipped":
            skipped += 1
        else:
            errors += 1

    return {
        "status": "ok",
        "total": len(targets),
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }


def sync_full_history(force: bool = False) -> dict:
    """Download and store COTAHIST data for ALL years (2010 to current).

    [v3] Also available as ``sync_all()`` for consistency with other data sources
    (BCB SGS, B3 dividends, B3 index all use ``sync_all``).
    """
    """Sync all years from FIRST_YEAR (2010) to current year.

    Args:
        force: Re-download even if already synced.
    """
    current_year = datetime.now().year
    years = list(range(FIRST_YEAR, current_year + 1))
    return sync(years=years, force=force)


# ── Internal: sync a single year ─────────────────────────────────────────────

def _sync_year(year: int, force: bool = False) -> dict:
    """Download, parse, and store COTAHIST data for a single year."""
    t0 = time.time()
    now = _now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        # Check if already synced
        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE year=?", (year,),
            ).fetchone()
            if existing:
                return {
                    "status": "skipped",
                    "year": year,
                    "rows": existing["rows_added"],
                    "synced_at": existing["synced_at"],
                }

        # Download ZIP
        url = COTAHIST_URL.format(year=year)
        _progress(f"[cotahist] Downloading {url}...")
        try:
            resp = httpx.get(url, timeout=120, follow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "year": year,
                    "error": f"Download failed: {e}"}

        if resp.content[:2] != b"PK":
            return {"status": "error", "year": year,
                    "error": "Response is not a ZIP file"}

        _progress(f"[cotahist] Downloaded {len(resp.content):,} bytes")

        # Parse + store (streaming)
        rows_added = _parse_and_store(conn, resp.content, year, now)
        duration = round(time.time() - t0, 1)

        # Record sync state
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (year, synced_at, rows_added, duration_s) "
            "VALUES (?, ?, ?, ?)",
            (year, now, rows_added, duration),
        )
        conn.commit()

        _progress(f"[cotahist] Year {year}: {rows_added:,} rows in {duration}s")
        return {
            "status": "ok",
            "year": year,
            "rows": rows_added,
            "duration_s": duration,
            "synced_at": now,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "year": year,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()}
    finally:
        conn.close()


# ── Internal: parse + store (streaming) ──────────────────────────────────────

def _parse_and_store(conn: sqlite3.Connection, zip_bytes: bytes, year: int,
                     ingested_at: str) -> int:
    """Extract ZIP, parse fixed-width lines (streaming), batch insert to SQLite.

    Only processes record type '01' (daily quote records). Skips '00' (header) and '99' (trailer).
    [v1.0.1] Also filters by BDI code (equities, FIIs, ETFs, fractional only).
    [v1.2] Derivatives (options/term/forward) are written to a separate
           `cotahist_derivatives` table in the same DB. Rows with BDI codes in
           DERIVATIVES_BDI_FILTER are parsed + the ticker is decoded (underlying,
           option_type, strike) + written to the derivatives table.
    Uses batch inserts (BATCH_SIZE) for performance.
    """
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

    # Find the TXT file inside the ZIP
    txt_name = next(
        (n for n in zf.namelist() if n.lower().endswith(('.txt', '.csv'))),
        zf.namelist()[0] if zf.namelist() else None,
    )
    if not txt_name:
        raise ValueError("No TXT file found in COTAHIST ZIP")

    _progress(f"[cotahist] Parsing {txt_name} (streaming)...")

    # Delete old data for this year (equities table)
    conn.execute(f"DELETE FROM cotahist WHERE refdate LIKE '{year}%'")
    # [v1.2] Also delete old derivatives data for this year.
    try:
        _ensure_deriv_schema(conn)
        conn.execute(f"DELETE FROM cotahist_derivatives WHERE refdate LIKE '{year}%'")
    except Exception:
        pass  # derivatives table might not exist yet on first run
    conn.commit()

    # Build column list for equities (exclude id + _ingested_at)
    cols = [c[0] for c in COTAHIST_LAYOUT]  # all layout columns
    col_str = ", ".join(cols) + ", _ingested_at"
    placeholders = ", ".join(["?"] * (len(cols) + 1))
    insert_sql = f"INSERT INTO cotahist ({col_str}) VALUES ({placeholders})"

    # [v1.2] Build column list for derivatives (same layout cols + derived cols)
    deriv_cols = cols + ["underlying", "option_type", "expiration_month", "strike_parsed", "derivative_type"]
    deriv_col_str = ", ".join(deriv_cols) + ", _ingested_at"
    deriv_placeholders = ", ".join(["?"] * (len(deriv_cols) + 1))
    deriv_insert_sql = f"INSERT INTO cotahist_derivatives ({deriv_col_str}) VALUES ({deriv_placeholders})"

    rows_added = 0
    deriv_rows_added = 0
    batch: list[tuple] = []
    deriv_batch: list[tuple] = []

    # Stream the file line by line
    with zf.open(txt_name) as f:
        raw = io.TextIOWrapper(f, encoding=CSV_ENCODING, errors="replace")
        for line in raw:
            line = line.rstrip("\n\r")
            if len(line) < 245:
                continue
            # Only process daily quote records (type 01). Skip header (00) and trailer (99).
            if line[:2] != "01":
                continue

            # [v1.0.1] Filter by BDI code.
            bdi_str = line[10:12].strip()  # positions 11-12 (0-based: 10-11)
            try:
                bdi = int(bdi_str) if bdi_str else 0
            except ValueError:
                bdi = 0

            if bdi in BDI_FILTER:
                # Equities path (existing).
                row = _parse_line(line)
                if row is None:
                    continue
                values = tuple(row.get(c, None) for c in cols) + (ingested_at,)
                batch.append(values)
                if len(batch) >= BATCH_SIZE:
                    conn.executemany(insert_sql, batch)
                    conn.commit()
                    rows_added += len(batch)
                    batch = []
                    if rows_added % 500000 == 0:
                        _progress(f"[cotahist] {rows_added:,} rows stored...")

            elif bdi in DERIVATIVES_BDI_FILTER:
                # [v1.2] Derivatives path — parse + decode ticker + write to derivatives table.
                row = _parse_line(line)
                if row is None:
                    continue
                # Parse the option ticker to extract underlying, type, strike.
                symbol = row.get("symbol", "")
                parsed = parse_option_ticker(symbol)
                if parsed:
                    row["underlying"] = parsed["underlying"]
                    row["option_type"] = parsed["option_type"]
                    row["expiration_month"] = parsed["expiration_month"]
                    row["strike_parsed"] = parsed["strike_parsed"]
                else:
                    # Not an option ticker (e.g. term/forward/exercise) — store with NULLs.
                    row["underlying"] = None
                    row["option_type"] = None
                    row["expiration_month"] = None
                    row["strike_parsed"] = None
                # [v1.1] Populate derivative_type from BDI code.
                row["derivative_type"] = BDI_TO_DERIVATIVE_TYPE.get(bdi)

                deriv_values = tuple(row.get(c, None) for c in deriv_cols) + (ingested_at,)
                deriv_batch.append(deriv_values)
                if len(deriv_batch) >= BATCH_SIZE:
                    conn.executemany(deriv_insert_sql, deriv_batch)
                    conn.commit()
                    deriv_rows_added += len(deriv_batch)
                    deriv_batch = []
                    if deriv_rows_added % 500000 == 0:
                        _progress(f"[cotahist_deriv] {deriv_rows_added:,} derivatives rows stored...")

    # Insert remaining equities
    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()
        rows_added += len(batch)

    # [v1.2] Insert remaining derivatives
    if deriv_batch:
        conn.executemany(deriv_insert_sql, deriv_batch)
        conn.commit()
        deriv_rows_added += len(deriv_batch)

    if deriv_rows_added > 0:
        _progress(f"[cotahist_deriv] {deriv_rows_added:,} derivatives rows stored for {year}")

    return rows_added


def _parse_line(line: str) -> dict | None:
    """Parse one COTAHIST fixed-width line into a dict.

    Handles:
    - Text columns: strip whitespace
    - Integer columns: int()
    - Numeric (real) columns: int(value) / 100.0 (B3 implicit 2 decimals)
    - Date: YYYYMMDD → YYYY-MM-DD
    """
    row = {}
    for name, typ, start, end, _ in COTAHIST_LAYOUT:
        # B3 uses 1-based positions; Python is 0-based
        val = line[start - 1:end].strip()

        if not val:
            row[name] = None
            continue

        try:
            if name in NUMERIC_COLS:
                # B3 stores prices without decimal point (implicit /100)
                # e.g., "539800000000" → 53980000.00
                row[name] = int(val) / 100.0
            elif name in INTEGER_COLS:
                row[name] = int(val)
            elif name == "refdate":
                # YYYYMMDD → YYYY-MM-DD
                row[name] = f"{val[:4]}-{val[4:6]}-{val[6:8]}" if len(val) == 8 else val
            elif name == "maturity":
                # YYYYMMDD → YYYY-MM-DD (may be empty for non-derivatives)
                row[name] = f"{val[:4]}-{val[4:6]}-{val[6:8]}" if len(val) == 8 and val != "00000000" else None
            else:
                row[name] = val
        except (ValueError, TypeError):
            row[name] = val  # keep as string if parse fails

    return row


# [v3] Alias for consistency with other data sources (BCB SGS, B3 dividends, etc.)
sync_all = sync_full_history
