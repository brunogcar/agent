"""
skills/b3/b3_dividends/query_engine.py
Query local dividends data with filters, date ranges, and column selection.

All dates are stored as YYYY-MM-DD (ISO), so string comparison works correctly
for range queries. No conversion needed at query time.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from skills.b3.b3_dividends.dividends_catalog import (
    B3_SCHEMAS,
    get_schema,
    get_columns,
)
from skills.b3.b3_dividends.storage import _db_path

SCHEMA_MAP: dict[str, str] = {
    "cash": "CashDividends",
    "stock": "StockDividends",
    "subscription": "Subscriptions",
}


def query(
    ticker: str | None = None,
    dividend_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: dict | None = None,
    columns: list[str] | None = None,
    limit: int = 100,
    base_dir: Path | None = None,
) -> dict:
    """Query local dividends data with filters.

    Args:
        ticker: Filter by full ticker (e.g., "PETR4", "VALE3"). Case-insensitive.
        dividend_type: "cash", "stock", or "subscription". If None, queries all schemas.
        start_date: Filter by approved_on >= YYYY-MM-DD.
        end_date: Filter by approved_on <= YYYY-MM-DD.
        filters: Additional {column: value} equality filters.
        columns: Specific columns to return. If None, returns all.
        limit: Max rows per schema. Default 100.
        base_dir: Root B3 storage directory. If None, uses cfg.memory_root / "b3".

    Returns:
        Dict with keys:
            status: "ok" | "error"
            schemas: Dict mapping schema name → {"rows": [...], "count": int}
            limit: The applied limit
            error: Error message (if status == "error")

    Note:
        Dates must be provided as YYYY-MM-DD. The storage layer normalizes
        B3's DD/MM/YYYY to ISO at sync time, so queries work without conversion.
    """
    from core.config import cfg

    if base_dir is None:
        base_dir = cfg.memory_root / "b3"

    if dividend_type and dividend_type not in SCHEMA_MAP:
        return {
            "status": "error",
            "error": f"Unknown dividend_type '{dividend_type}'. Use: cash, stock, subscription",
            "schemas": {},
            "limit": limit,
        }

    target_schema = SCHEMA_MAP.get(dividend_type) if dividend_type else None
    schemas_to_query = [target_schema] if target_schema else list(B3_SCHEMAS.keys())
    results: dict[str, dict] = {}

    for name in schemas_to_query:
        schema = get_schema(name)
        table = schema["table"]
        known = set(get_columns(name).keys())
        db_path = _db_path(name, base_dir)

        if not db_path.exists():
            results[name] = {"rows": [], "count": 0, "error": f"{db_path.name} not found"}
            continue

        where_parts: list[str] = []
        where_vals: list[Any] = []

        if ticker:
            # Full ticker match — no truncation. PETR3 and PETR4 are distinct.
            where_parts.append("ticker = ?")
            where_vals.append(ticker.upper().strip())

        if start_date:
            where_parts.append("approved_on >= ?")
            where_vals.append(start_date)

        if end_date:
            where_parts.append("approved_on <= ?")
            where_vals.append(end_date)

        for col, val in (filters or {}).items():
            if col in known:
                where_parts.append(f"{col} = ?")
                where_vals.append(val)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        if columns:
            valid_cols = [c for c in columns if c in known]
            select_sql = ", ".join(valid_cols) if valid_cols else "*"
        else:
            select_sql = "*"

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                # Fetch rows with limit
                rows = conn.execute(
                    f"SELECT {select_sql} FROM {table} {where_sql} LIMIT ?",
                    where_vals + [limit],
                ).fetchall()

                # Count total matching rows (without limit)
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} {where_sql}",
                    where_vals,
                ).fetchone()
                count = count_row[0] if count_row else 0

            finally:
                conn.close()

            results[name] = {
                "rows": [dict(r) for r in rows],
                "count": count,
            }

        except Exception as e:
            results[name] = {"rows": [], "count": 0, "error": str(e)}

    return {"status": "ok", "schemas": results, "limit": limit}
