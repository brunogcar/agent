"""data_sources/cvm/cad/sync_engine.py -- Download cad_cia_aberta.csv and populate cad.db.

CAD is a single CSV file (~1.5MB, ~3500 companies) updated weekly.
Unlike DFP/ITR/FRE/IPE (ZIP files), CAD is a direct CSV download — no ZIP.

The file is a complete snapshot each time, so sync does a full replace
(DELETE + INSERT). No incremental/dedup logic needed.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import sys
from datetime import datetime

import requests

from core.tracer import tracer
from data_sources.cvm._db import connect_cad, cad_db_path, cnpj_digits
from data_sources.cvm.cad.catalog import (
    CSV_URL, CSV_ENCODING, CSV_DELIMITER, ALL_COLS, SCHEMA_SQL,
)


def sync(force: bool = False, trace_id: str = "", verbose: bool = True) -> dict:
    """Download cad_cia_aberta.csv from CVM and store to cad.db.

    Args:
        force: Re-download even if already synced today.
        trace_id: Tracer ID for logging.
        verbose: Print progress to stderr.

    Returns:
        Dict with sync status, row count, file size.
    """
    tid = trace_id or ""

    def _log(msg: str) -> None:
        if verbose:
            print(f"[cad] {msg}", file=sys.stderr, flush=True)

    # Check if already synced today (unless force)
    if not force:
        conn = connect_cad(read_only=False)
        _ensure_schema(conn)
        existing = conn.execute(
            "SELECT synced_at FROM sync_state ORDER BY synced_at DESC LIMIT 1"
        ).fetchone()
        if existing:
            synced_date = existing["synced_at"][:10] if existing["synced_at"] else ""
            today = datetime.now().strftime("%Y-%m-%d")
            if synced_date == today:
                conn.close()
                _log(f"skip (already synced today, use force=True to re-download)")
                return {"status": "skipped", "reason": "already synced today"}

    _log(f"downloading {CSV_URL}")
    tracer.step(tid, "cad_sync", f"Downloading: {CSV_URL}")

    try:
        resp = requests.get(CSV_URL, timeout=60)
        resp.raise_for_status()
        csv_text = resp.content.decode(CSV_ENCODING, errors="replace")
    except Exception as e:
        return {"status": "error", "error": f"Download failed: {e}"}

    _log(f"downloaded {len(csv_text) / 1024:.1f} KB")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=CSV_DELIMITER)
    rows = list(reader)
    if not rows:
        return {"status": "error", "error": "CSV parsed to zero rows"}

    _log(f"parsed {len(rows):,} rows")

    # Store — full replace (file is a complete snapshot)
    conn = connect_cad(read_only=False)
    _ensure_schema(conn)
    try:
        conn.execute("DELETE FROM cia_aberta")

        placeholders = ", ".join("?" * len(ALL_COLS))
        insert_sql = f"INSERT INTO cia_aberta VALUES ({placeholders})"

        batch = []
        for row in rows:
            vals = []
            for c in ALL_COLS:
                val = str(row.get(c, "") or "").strip()
                # [v1.1] Normalize CNPJ columns to 14 plain digits
                if c in ("CNPJ_CIA", "CNPJ_AUDITOR"):
                    val = cnpj_digits(val)
                vals.append(val)
            batch.append(tuple(vals))

        conn.executemany(insert_sql, batch)

        synced_at = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO sync_state (synced_at, rows, size_kb) VALUES (?, ?, ?)",
            (synced_at, len(rows), round(len(csv_text) / 1024, 1)),
        )
        conn.commit()

        _log(f"stored {len(rows):,} companies")
        tracer.step(tid, "cad_sync", f"Stored {len(rows)} companies")

        return {
            "status": "ok",
            "rows": len(rows),
            "size_kb": round(len(csv_text) / 1024, 1),
            "synced_at": synced_at,
        }
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
