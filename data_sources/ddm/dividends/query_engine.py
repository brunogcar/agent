"""data_sources/ddm/dividends/query_engine.py -- Read-only queries against dividends.db.

Functions:
  - dividends_list(order_by="value", direction="desc", limit=0)
  - last_value(ticker, limit=10)
  - search(query, limit=50)
  - ticker_history(ticker)
  - summary()

All queries open a read-only SQLite URI connection (fails if DB missing).
"""

from __future__ import annotations

from data_sources.ddm.dividends.catalog import SORT_KEYS, connect, db_path


def dividends_list(order_by: str = "value", direction: str = "desc",
                   limit: int = 0) -> dict:
    """List all dividends sorted by a column.

    Args:
        order_by:  Sort key. One of SORT_KEYS ('value' | 'ticker' | 'tipo' |
                   'record_date' | 'ex_date' | 'payment_date').
                   Default: 'value'.
        direction: 'desc' or 'asc'. Default: 'desc'.
        limit:     Max rows. 0 = all. Default: 0.

    Returns:
        {"status": "ok", "count": <int>, "order_by": ..., "direction": ...,
         "dividends": [{ticker, tipo, value, record_date, ex_date,
                        payment_date}, ...]}
    """
    if order_by not in SORT_KEYS:
        return {"status": "error",
                "error": f"order_by must be one of {SORT_KEYS} (got '{order_by}')"}
    if direction not in ("asc", "desc"):
        return {"status": "error",
                "error": f"direction must be 'asc' or 'desc' (got '{direction}')"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # order_by + direction are validated against SORT_KEYS whitelist.
        sql = (f"SELECT ticker, tipo, value, record_date, ex_date, payment_date "
               f"FROM dividends ORDER BY {order_by} {direction.upper()}"
               + (" LIMIT ?" if limit and limit > 0 else ""))
        params: tuple = (limit,) if limit and limit > 0 else ()
        rows = list(conn.execute(sql, params).fetchall())

        return {
            "status":    "ok",
            "count":     len(rows),
            "order_by":  order_by,
            "direction": direction,
            "dividends": [
                {"ticker":       r["ticker"],
                 "tipo":         r["tipo"],
                 "value":        r["value"],
                 "record_date":  r["record_date"],
                 "ex_date":      r["ex_date"],
                 "payment_date": r["payment_date"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def last_value(ticker: str = "", limit: int = 10) -> dict:
    """Get the latest dividends for a specific ticker (record_date DESC).

    Args:
        ticker: B3 ticker (e.g. 'BBDC3'). Required.
        limit:  Max rows. Default: 10.

    Returns:
        {"status": "ok", "ticker": ..., "count": <int>,
         "dividends": [{...}, ...]}
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = list(conn.execute(
            "SELECT ticker, tipo, value, record_date, ex_date, payment_date "
            "FROM dividends WHERE ticker=? "
            "ORDER BY record_date DESC" + (" LIMIT ?" if limit and limit > 0 else ""),
            (ticker, limit) if limit and limit > 0 else (ticker,),
        ).fetchall())

        if not rows:
            return {"status": "not_found", "ticker": ticker,
                    "error": f"No dividends for ticker '{ticker}'"}

        return {
            "status":    "ok",
            "ticker":    ticker,
            "count":     len(rows),
            "dividends": [
                {"ticker":       r["ticker"],
                 "tipo":         r["tipo"],
                 "value":        r["value"],
                 "record_date":  r["record_date"],
                 "ex_date":      r["ex_date"],
                 "payment_date": r["payment_date"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def search(query: str = "", limit: int = 50) -> dict:
    """Search dividends by ticker fragment (case-insensitive).

    Args:
        query: Ticker fragment. Required.
        limit: Max results. Default: 50.

    Returns:
        {"status": "ok", "count": <int>,
         "dividends": [{...}, ...]}
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = list(conn.execute(
            "SELECT ticker, tipo, value, record_date, ex_date, payment_date "
            "FROM dividends WHERE UPPER(ticker) LIKE UPPER(?) "
            "ORDER BY record_date DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall())

        return {
            "status":    "ok",
            "count":     len(rows),
            "dividends": [
                {"ticker":       r["ticker"],
                 "tipo":         r["tipo"],
                 "value":        r["value"],
                 "record_date":  r["record_date"],
                 "ex_date":      r["ex_date"],
                 "payment_date": r["payment_date"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def ticker_history(ticker: str = "") -> dict:
    """All dividends for a specific ticker (all dates, all tipos).

    Convenience wrapper for last_value(ticker, limit=0).
    """
    return last_value(ticker=ticker, limit=0)


def summary() -> dict:
    """Overview stats for the dividend agenda.

    Returns:
        {"status": "ok", "total_dividends": <int>, "total_value": <float>,
         "biggest": {"ticker", "tipo", "value", "record_date"} | None,
         "next_payment_date": <str> | "",
         "by_tipo": {"Dividendo": <int>, "JCP": <int>}}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        total = conn.execute(
            "SELECT COUNT(*) as n FROM dividends"
        ).fetchone()["n"]

        if not total:
            return {"status": "ok", "total_dividends": 0, "total_value": 0.0,
                    "biggest": None, "next_payment_date": "",
                    "by_tipo": {"Dividendo": 0, "JCP": 0}}

        total_value_row = conn.execute(
            "SELECT COALESCE(SUM(value), 0.0) as s FROM dividends"
        ).fetchone()
        total_value = total_value_row["s"] if total_value_row else 0.0

        biggest_row = conn.execute(
            "SELECT ticker, tipo, value, record_date "
            "FROM dividends ORDER BY value DESC LIMIT 1"
        ).fetchone()
        biggest = None
        if biggest_row:
            biggest = {
                "ticker":      biggest_row["ticker"],
                "tipo":        biggest_row["tipo"],
                "value":       biggest_row["value"],
                "record_date": biggest_row["record_date"],
            }

        # Next payment date = the earliest payment_date strictly in the
        # future vs. today (or, if all are in the past, the latest one).
        today_iso = _today_iso()
        next_row = conn.execute(
            "SELECT payment_date FROM dividends "
            "WHERE payment_date IS NOT NULL AND payment_date >= ? "
            "ORDER BY payment_date ASC LIMIT 1",
            (today_iso,),
        ).fetchone()
        next_payment_date = ""
        if next_row and next_row["payment_date"]:
            next_payment_date = next_row["payment_date"]
        else:
            latest_row = conn.execute(
                "SELECT payment_date FROM dividends "
                "WHERE payment_date IS NOT NULL "
                "ORDER BY payment_date DESC LIMIT 1"
            ).fetchone()
            if latest_row and latest_row["payment_date"]:
                next_payment_date = latest_row["payment_date"]

        by_tipo = {"Dividendo": 0, "JCP": 0}
        tipo_rows = conn.execute(
            "SELECT tipo, COUNT(*) as n FROM dividends GROUP BY tipo"
        ).fetchall()
        for r in tipo_rows:
            tipo = r["tipo"] or "?"
            by_tipo[tipo] = r["n"]

        return {
            "status":            "ok",
            "total_dividends":   total,
            "total_value":       total_value,
            "biggest":           biggest,
            "next_payment_date": next_payment_date,
            "by_tipo":           by_tipo,
        }
    finally:
        conn.close()


def _today_iso() -> str:
    """Return today's date as YYYY-MM-DD (UTC)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

