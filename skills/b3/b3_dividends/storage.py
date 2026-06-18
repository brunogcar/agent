"""
skills/b3/b3_dividends/storage.py
SQLite storage layer for B3 dividends data.

Handles:
  - DB path resolution (isolated under memory_db/b3/)
  - Table creation with PRIMARY KEY
  - Type coercion (text → real/int, with None on failure)
  - Chunked batch inserts (avoids SQLite parameter limit)
  - Per-ticker REPLACE semantics (delete old → insert new)

All three schemas share the same DB file (dividends.db) but live in separate tables.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from skills.b3.b3_dividends.dividends_catalog import (
    get_schema,
    get_columns,
    get_numeric_cols,
    get_integer_cols,
    build_create_sql,
)

CHUNK_SIZE = 500  # SQLite parameter limit is ~999; stay well below it


def _db_path(name: str, base_dir: Path) -> Path:
    """Resolve the SQLite DB path for a schema.

    Args:
        name: Schema name.
        base_dir: Root directory for B3 storage (e.g., memory_db/b3).

    Returns:
        Path to the .db file.
    """
    schema = get_schema(name)
    return base_dir / schema["db_file"]


def _coerce_value(value: Any, col_name: str, numeric_cols: set[str], integer_cols: set[str]) -> Any:
    """Coerce a raw string value to the appropriate SQLite type.

    Args:
        value: Raw value (usually string from JSON).
        col_name: Column name (used to look up type).
        numeric_cols: Set of columns that should be float/real.
        integer_cols: Set of columns that should be int.

    Returns:
        float, int, str, or None. Returns None on parse failure for numeric
        columns (prevents polluting the DB with "N/A" strings in REAL columns).
    """
    if value is None:
        return None
    v = str(value).strip()
    if not v or v.lower() in ("null", "none", "nan", "-", "n/a"):
        return None

    if col_name in numeric_cols:
        try:
            # B3 uses comma as decimal separator in some locales
            return float(v.replace(",", "."))
        except (ValueError, TypeError):
            return None  # Was: return v (string fallback — bad for REAL columns)

    if col_name in integer_cols:
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    return v


def store_to_sqlite(name: str, data_rows: list[dict], ticker: str, base_dir: Path) -> int:
    """Store parsed rows to SQLite, replacing existing data for this ticker.

    Uses a single connection for all operations (table creation, index creation,
    delete old rows, insert new rows). This is efficient because all three schemas
    share the same DB file.

    Args:
        name: Schema name (e.g., "CashDividends").
        data_rows: List of parsed row dicts from parser.py.
        ticker: Full ticker symbol (e.g., "PETR4").
        base_dir: Root B3 storage directory.

    Returns:
        Number of rows inserted.

    Note:
        Deletes existing rows for this ticker before inserting, ensuring no
        stale data from previous syncs. Uses chunked executemany to stay
        within SQLite parameter limits.
    """
    schema = get_schema(name)
    table = schema["table"]
    db_path = _db_path(name, base_dir)
    known_cols = set(get_columns(name).keys())
    numeric = get_numeric_cols(name)
    integer = get_integer_cols(name)
    ingested_at = datetime.utcnow().isoformat()

    # Build insert SQL: source columns + metadata
    insert_cols = list(known_cols) + ["_ingested_at"]
    placeholders = ", ".join("?" * len(insert_cols))
    insert_sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            # Create table if not exists (includes PRIMARY KEY and _ingested_at)
            conn.execute(build_create_sql(name))

            # Delete existing rows for this ticker — REPLACE semantics per ticker
            if "ticker" in known_cols:
                conn.execute(f"DELETE FROM {table} WHERE ticker = ?", (ticker,))

            # Create indexes if defined
            for idx_col in schema.get("indexes", []):
                if idx_col in known_cols:
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS idx_{table}_{idx_col} ON {table}({idx_col})"
                    )

            rows_inserted = 0
            chunk: list[tuple] = []

            for row in data_rows:
                values = [
                    _coerce_value(row.get(col, ""), col, numeric, integer)
                    for col in insert_cols[:-1]  # exclude _ingested_at
                ]
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


def get_row_count(name: str, ticker: str | None, base_dir: Path) -> int:
    """Count rows in a schema table, optionally filtered by ticker.

    Args:
        name: Schema name.
        ticker: If provided, count only rows for this ticker.
        base_dir: Root B3 storage directory.

    Returns:
        Row count.
    """
    schema = get_schema(name)
    table = schema["table"]
    db_path = _db_path(name, base_dir)

    if not db_path.exists():
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        if ticker:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE ticker = ?", (ticker,))
        else:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_db_size_kb(name: str, base_dir: Path) -> float:
    """Return the DB file size in KB.

    Args:
        name: Schema name (used to resolve DB file).
        base_dir: Root B3 storage directory.

    Returns:
        Size in KB, rounded to 1 decimal.
    """
    db_path = _db_path(name, base_dir)
    if not db_path.exists():
        return 0.0
    return round(db_path.stat().st_size / 1024, 1)
