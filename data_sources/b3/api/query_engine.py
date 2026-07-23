"""data_sources/b3/api/query_engine.py -- Query B3 market data.

Query instruments (tickers, ISIN, company names), trades (prices, volume),
and other B3 tables stored in local SQLite DBs.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.b3.api.catalog import B3_TABLES, connect, db_path


def query(
    table: str = "instruments",
    ticker: str = "",
    columns: list[str] | None = None,
    filters: dict | None = None,
    limit: int = 100,
) -> dict:
    """Query B3 data from local SQLite DB.

    Args:
        table: Table name (instruments, trades, after_hours, derivatives).
        ticker: Ticker symbol filter (e.g., "PETR4"). Empty = all.
        columns: Specific columns to return. None = all.
        filters: Dict of {column: value} for additional filtering.
        limit: Max rows. Default: 100.

    Returns:
        Dict with rows + column names.
    """
    if table not in B3_TABLES:
        return {"status": "error",
                "error": f"Unknown table '{table}'. Available: {list(B3_TABLES.keys())}"}

    try:
        conn = connect(table, read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        db_table = B3_TABLES[table]["table"]

        # Get actual column names from the table
        col_rows = conn.execute(f"PRAGMA table_info({db_table})").fetchall()
        if not col_rows:
            return {"status": "error", "error": f"Table {db_table} has no columns. Run sync first."}
        all_cols = [r["name"] for r in col_rows if r["name"] != "_ingested_at"]

        # Select columns
        if columns:
            select_cols = [c for c in columns if c in all_cols]
            if not select_cols:
                select_cols = all_cols
        else:
            select_cols = all_cols
        select_str = ", ".join(select_cols)

        # Build WHERE
        conditions = []
        params: list = []

        if ticker and "TckrSymb" in all_cols:
            conditions.append("TckrSymb = ?")
            params.append(ticker.upper())

        if filters:
            for col, val in filters.items():
                if col in all_cols:
                    conditions.append(f"{col} LIKE ?")
                    params.append(f"%{val}%")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = conn.execute(
            f"SELECT {select_str} FROM {db_table} {where} LIMIT ?",
            params + [limit],
        ).fetchall()

        if not rows:
            return {"status": "not_found", "table": table, "count": 0, "rows": []}

        return {
            "status": "ok",
            "table": table,
            "count": len(rows),
            "columns": select_cols,
            "rows": [dict(r) for r in rows],
        }

    finally:
        conn.close()


def lookup_ticker(ticker: str = "") -> dict:
    """Look up a single ticker in the instruments table.

    Returns company name, ISIN, segment, governance level, etc.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    result = query(table="instruments", ticker=ticker, limit=1)
    if result["status"] == "ok" and result["rows"]:
        return {"status": "ok", "ticker": ticker.upper(), "instrument": result["rows"][0]}
    return {"status": "not_found", "ticker": ticker, "error": f"Ticker '{ticker}' not found in instruments table"}


def search_company(name: str = "", limit: int = 20) -> dict:
    """Search instruments by company name fragment."""
    if not name:
        return {"status": "error", "error": "name is required"}

    result = query(
        table="instruments",
        filters={"CrpnNm": name},
        limit=limit,
    )
    if result["status"] == "ok":
        return {
            "status": "ok",
            "query": name,
            "count": result["count"],
            "instruments": result["rows"],
        }
    return result


def status() -> dict:
    """Show sync status for all B3 tables."""
    results = {"status": "ok", "tables": {}}

    for table_name, table_info in B3_TABLES.items():
        path = db_path(table_name)
        if not path.exists():
            results["tables"][table_name] = {
                "status": "not_synced",
                "path": str(path),
            }
            continue

        try:
            conn = connect(table_name, read_only=True)
            try:
                count = conn.execute(
                    f"SELECT COUNT(*) as n FROM {table_info['table']}"
                ).fetchone()["n"]

                sync_rows = conn.execute(
                    "SELECT * FROM sync_state WHERE table_name=? ORDER BY date DESC LIMIT 1",
                    (table_name,),
                ).fetchone()

                results["tables"][table_name] = {
                    "status": "ok",
                    "rows": count,
                    "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                    "last_sync": {
                        "date": sync_rows["date"] if sync_rows else "",
                        "synced_at": sync_rows["synced_at"] if sync_rows else "",
                        "row_count": sync_rows["row_count"] if sync_rows else 0,
                    } if sync_rows else None,
                }
            except sqlite3.OperationalError:
                results["tables"][table_name] = {
                    "status": "not_synced",
                    "message": "DB exists but tables not created. Run sync first.",
                }
            finally:
                conn.close()
        except Exception as e:
            results["tables"][table_name] = {"status": "error", "error": str(e)}

    return results
