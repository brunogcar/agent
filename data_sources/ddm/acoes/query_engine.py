"""data_sources/ddm/acoes/query_engine.py -- Read-only queries against acoes.db.

Functions:
  - stocks_list(order_by, direction, limit) - all stocks sorted
  - stocks(order_by, direction, limit)      - alias for stocks_list (user-facing)
  - last_value(ticker)                       - latest snapshot for one ticker
  - search(query, limit)                     - LIKE search over ticker + name
  - summary()                                - overview stats

All queries open a read-only SQLite URI connection (fails if DB missing).
"""

from __future__ import annotations

from data_sources.ddm.acoes.catalog import (
    connect, db_path,
)

# Whitelist of sortable columns (defends against SQL injection since
# order_by + direction are interpolated into the ORDER BY clause).
_SORT_COLUMNS = {
    "ticker":     "ticker",
    "name":       "name",
    "negocios":   "negocios",
    "last_price": "last_price",
    "variation":  "variation",
}


def _row_to_dict(row) -> dict:
    return {
        "ticker":     row["ticker"],
        "name":       row["name"],
        "negocios":   row["negocios"],
        "last_price": row["last_price"],
        "variation":  row["variation"],
        "ref_date":   row["ref_date"],
        "synced_at":  row["synced_at"],
    }


def stocks_list(order_by: str = "negocios", direction: str = "desc",
                limit: int = 0) -> dict:
    """Query all stocks, sorted by the specified column.

    Args:
        order_by:  'ticker', 'name', 'negocios', 'last_price', 'variation'.
                   Default: 'negocios'.
        direction: 'asc' or 'desc'. Default: 'desc'.
        limit:     Max results. 0 = all. Default: 0.

    Returns:
        {"status": "ok", "count": <int>,
         "stocks": [{ticker, name, negocios, last_price, variation,
                     ref_date, synced_at}, ...]}
    """
    col = _SORT_COLUMNS.get(order_by, "negocios")
    direction = "DESC" if direction.lower() == "desc" else "ASC"

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        sql = (
            "SELECT ticker, name, negocios, last_price, variation, "
            "ref_date, synced_at FROM stocks "
            f"ORDER BY {col} {direction}"
        )
        params: tuple = ()
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (limit,)

        rows = list(conn.execute(sql, params).fetchall())
        return {
            "status": "ok",
            "count":  len(rows),
            "stocks": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def last_value(ticker: str = "") -> dict:
    """Get the most recent snapshot for a single ticker.

    Returns:
        {"status": "ok", "ticker": <str>, "name": ..., "negocios": ...,
         "last_price": ..., "variation": ..., "ref_date": ...,
         "synced_at": ...}
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        row = conn.execute(
            "SELECT ticker, name, negocios, last_price, variation, "
            "ref_date, synced_at FROM stocks WHERE ticker=?",
            (ticker.upper(),),
        ).fetchone()
        if not row:
            return {"status": "not_found", "ticker": ticker,
                    "error": f"No snapshot for ticker '{ticker}'"}
        out = _row_to_dict(row)
        out["status"] = "ok"
        return out
    finally:
        conn.close()


def search(query: str = "", limit: int = 50) -> dict:
    """Search stocks by ticker or name fragment (case-insensitive LIKE).

    Returns:
        {"status": "ok", "count": <int>,
         "stocks": [{ticker, name, negocios, last_price, variation,
                     ref_date, synced_at}, ...]}
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        pattern = f"%{query}%"
        sql = (
            "SELECT ticker, name, negocios, last_price, variation, "
            "ref_date, synced_at FROM stocks "
            "WHERE UPPER(ticker) LIKE UPPER(?) OR UPPER(name) LIKE UPPER(?) "
            "ORDER BY negocios DESC"
        )
        params = (pattern, pattern)
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (pattern, pattern, limit)

        rows = list(conn.execute(sql, params).fetchall())
        return {
            "status": "ok",
            "count":  len(rows),
            "stocks": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def summary() -> dict:
    """Overview: total stocks, most traded, biggest gainer, biggest loser.

    Returns:
        {"status": "ok", "total": <int>, "ref_date": <str>,
         "most_traded": {ticker, name, negocios},
         "biggest_gainer": {ticker, name, variation},
         "biggest_loser": {ticker, name, variation}}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        total_row = conn.execute("SELECT COUNT(*) as n FROM stocks").fetchone()
        total = total_row["n"] if total_row else 0
        if total == 0:
            return {"status": "ok", "total": 0, "ref_date": "",
                    "most_traded": None, "biggest_gainer": None,
                    "biggest_loser": None}

        ref_row = conn.execute(
            "SELECT ref_date FROM stocks WHERE ref_date IS NOT NULL "
            "ORDER BY ref_date DESC LIMIT 1"
        ).fetchone()
        ref_date = ref_row["ref_date"] if ref_row else ""

        most_traded_row = conn.execute(
            "SELECT ticker, name, negocios FROM stocks "
            "WHERE negocios IS NOT NULL ORDER BY negocios DESC LIMIT 1"
        ).fetchone()
        most_traded = dict(most_traded_row) if most_traded_row else None

        biggest_gainer_row = conn.execute(
            "SELECT ticker, name, variation FROM stocks "
            "WHERE variation IS NOT NULL ORDER BY variation DESC LIMIT 1"
        ).fetchone()
        biggest_gainer = dict(biggest_gainer_row) if biggest_gainer_row else None

        biggest_loser_row = conn.execute(
            "SELECT ticker, name, variation FROM stocks "
            "WHERE variation IS NOT NULL ORDER BY variation ASC LIMIT 1"
        ).fetchone()
        biggest_loser = dict(biggest_loser_row) if biggest_loser_row else None

        return {
            "status":         "ok",
            "total":          total,
            "ref_date":       ref_date,
            "most_traded":    most_traded,
            "biggest_gainer": biggest_gainer,
            "biggest_loser":  biggest_loser,
        }
    finally:
        conn.close()


def stocks(order_by: str = "negocios", direction: str = "desc",
          limit: int = 0) -> dict:
    """Alias for stocks_list (user-facing name for the MANIFEST `stocks` mode).

    Kept as a thin wrapper so the skill can call either ``stocks_list`` or
    ``stocks`` — the latter reads better in dashboard code (``stocks(...)``).
    """
    return stocks_list(order_by=order_by, direction=direction, limit=limit)


def _unused_path() -> str:
    """Expose db_path for diagnostics/tests (imported but not used in queries)."""
    return str(db_path())
