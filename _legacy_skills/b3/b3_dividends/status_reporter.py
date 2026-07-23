"""
skills/b3/b3_dividends/status_reporter.py
Accurate per-schema, per-ticker status reporting for B3 dividends.

Replaces the broken status() from the original dividends.py, which:
  - Reported the same ticker list for every schema
  - Summed grand total rows for every schema
  - Did not query actual DB counts

This version queries the DB directly for accurate per-schema, per-ticker counts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import cfg
from skills.b3.b3_dividends.dividends_catalog import B3_SCHEMAS, get_schema
from skills.b3.b3_dividends.storage import _db_path, get_row_count, get_db_size_kb

_STATE_FILE_NAME = ".sync_state.json"
_STATE_KEY = "b3_dividends"


def _load_state(base_dir: Path) -> dict:
    """Load sync state from JSON file."""
    path = base_dir / _STATE_FILE_NAME
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def status() -> dict:
    """Show accurate sync status for all dividend schemas.

    Returns:
        Dict with keys:
            status: "ok"
            schemas: Per-schema status dicts
            b3_dir: Root storage directory path

    Per-schema dict includes:
        - synced: bool (DB file exists)
        - db_path: Path to the DB
        - db_size_kb: File size
        - tickers: List of tickers with data in this schema
        - per_ticker: Dict mapping ticker → row count
        - total_rows: Sum of all rows in this schema
        - last_syncs: Dict mapping ticker → last sync ISO timestamp
    """
    base_dir = cfg.memory_root / "b3"
    state = _load_state(base_dir)
    file_state = state.get(_STATE_KEY, {})
    result: dict[str, dict] = {}

    for name in B3_SCHEMAS:
        schema = get_schema(name)
        db_path = _db_path(name, base_dir)
        db_exists = db_path.exists()

        # Get actual per-ticker counts from DB
        tickers_in_db: list[str] = []
        per_ticker: dict[str, int] = {}
        total_rows = 0

        if db_exists:
            # Query distinct tickers from the table
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(f"SELECT DISTINCT ticker FROM {schema['table']}")
                for row in cursor.fetchall():
                    ticker = row[0]
                    tickers_in_db.append(ticker)
                    count = get_row_count(name, ticker, base_dir)
                    per_ticker[ticker] = count
                    total_rows += count
            finally:
                conn.close()

        # Last sync times from state file (may include tickers not yet in DB)
        last_syncs: dict[str, str] = {}
        for ticker, info in file_state.items():
            last_syncs[ticker] = info.get("syncedAt", "")

        result[name] = {
            "synced": db_exists,
            "db_path": str(db_path),
            "db_size_kb": get_db_size_kb(name, base_dir),
            "tickers": sorted(tickers_in_db),
            "per_ticker": per_ticker,
            "total_rows": total_rows,
            "last_syncs": last_syncs,
        }

    return {
        "status": "ok",
        "schemas": result,
        "b3_dir": str(base_dir),
    }
