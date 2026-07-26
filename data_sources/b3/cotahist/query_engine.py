"""data_sources/b3/cotahist/query_engine.py -- Query COTAHIST data.

Read-only queries against cotahist.db:
  - query(ticker, date_from, date_to, year, limit) — OHLCV history
  - DB stats (years synced, row counts, date range)
"""

from __future__ import annotations

from data_sources.b3.cotahist.catalog import connect, db_path


def query(
    ticker: str = "",
    date_from: str = "",
    date_to: str = "",
    year: int = 0,
    limit: int = 100,
    market_type: int = 10,
) -> dict:
    """Query historical OHLCV from COTAHIST.

    Args:
        ticker: Ticker symbol (PETR4). Empty = all tickers.
        date_from: Start date YYYY-MM-DD.
        date_to: End date YYYY-MM-DD.
        year: Filter by year (e.g., 2025). Takes precedence over date_from/date_to.
        limit: Max rows. Default: 100.
        market_type: Filter by market type. 10=lote padrão (default, avoids
                     duplicate rows from fractional market). 0 = all market types.

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

        # [v1.0.1] Filter by market_type to avoid duplicate rows (lote padrão vs fracionário)
        if market_type > 0:
            conditions.append("market_type = ?")
            params.append(market_type)

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
