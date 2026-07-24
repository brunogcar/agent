"""data_sources/b3/cotahist/query_engine.py -- Query COTAHIST data.

Read-only queries against cotahist.db:
  - query(ticker, date_from, date_to, year, limit) — OHLCV history
  - status() — DB stats (years synced, row counts, date range)
"""

from __future__ import annotations

from data_sources.b3.cotahist.catalog import connect, db_path


def query(
    ticker: str = "",
    date_from: str = "",
    date_to: str = "",
    year: int = 0,
    limit: int = 100,
) -> dict:
    """Query historical OHLCV from COTAHIST.

    Args:
        ticker: Ticker symbol (PETR4). Empty = all tickers.
        date_from: Start date YYYY-MM-DD.
        date_to: End date YYYY-MM-DD.
        year: Filter by year (e.g., 2025). Takes precedence over date_from/date_to.
        limit: Max rows. Default: 100.

    Returns:
        Dict with OHLCV rows.
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        conditions = []
        params: list = []

        if ticker:
            conditions.append("symbol = ?")
            params.append(ticker.strip().upper())

        if year:
            conditions.append("refdate LIKE ?")
            params.append(f"{year}%")
        else:
            if date_from:
                conditions.append("refdate >= ?")
                params.append(date_from)
            if date_to:
                conditions.append("refdate <= ?")
                params.append(date_to)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = conn.execute(
            f"""SELECT refdate, symbol, corp_name, open, high, low, close,
                      average, volume, trade_count, contracts, isin,
                      market_type, bdi_code, best_bid, best_ask
               FROM cotahist {where}
               ORDER BY refdate DESC, symbol
               LIMIT ?""",
            params + [limit],
        ).fetchall()

        if not rows:
            return {"status": "not_found", "count": 0, "rows": []}

        return {
            "status": "ok",
            "count": len(rows),
            "rows": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def status() -> dict:
    """Show COTAHIST DB stats: years synced, row counts, date range."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "cotahist.db not found. Run sync first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "cotahist.db not found."}

    try:
        total = conn.execute("SELECT COUNT(*) as n FROM cotahist").fetchone()["n"]
        if total == 0:
            return {"status": "not_synced", "message": "cotahist.db exists but has no data. Run sync first."}

        # Date range
        min_date = conn.execute("SELECT MIN(refdate) as d FROM cotahist").fetchone()["d"]
        max_date = conn.execute("SELECT MAX(refdate) as d FROM cotahist").fetchone()["d"]

        # Distinct tickers
        tickers = conn.execute(
            "SELECT COUNT(DISTINCT symbol) as n FROM cotahist"
        ).fetchone()["n"]

        # Years synced
        years = conn.execute(
            "SELECT year, rows_added, synced_at, duration_s FROM sync_state ORDER BY year"
        ).fetchall()

        # DB size
        db_size_mb = round(path.stat().st_size / (1024 * 1024), 1)

        return {
            "status": "ok",
            "path": str(path),
            "db_size_mb": db_size_mb,
            "total_rows": total,
            "distinct_tickers": tickers,
            "date_range": {"from": min_date, "to": max_date},
            "years_synced": [
                {"year": y["year"], "rows": y["rows_added"],
                 "synced_at": y["synced_at"], "duration_s": y["duration_s"]}
                for y in years
            ],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()
