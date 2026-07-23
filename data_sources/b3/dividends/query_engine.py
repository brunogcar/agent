"""data_sources/b3/dividends/query_engine.py -- Query B3 dividends data."""

from __future__ import annotations

from data_sources.b3.dividends.catalog import connect, db_path


def dividends(ticker: str = "", limit: int = 50) -> dict:
    """Query cash dividends for a ticker.

    Args:
        ticker: Ticker symbol (e.g., PETR4).
        limit: Max results. Default: 50.

    Returns:
        Dict with dividends list.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT ticker, label, isin_code, approved_on, last_date_prior, rate, related_to, payment_date "
            "FROM cash_dividends WHERE ticker=? ORDER BY approved_on DESC LIMIT ?",
            (ticker.upper(), limit),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "ticker": ticker, "count": 0, "dividends": []}

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "count": len(rows),
            "dividends": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def stock_dividends(ticker: str = "", limit: int = 50) -> dict:
    """Query stock dividends (bonus shares) for a ticker."""
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT ticker, label, isin_code, approved_on, last_date_prior, factor, asset_issued "
            "FROM stock_dividends WHERE ticker=? ORDER BY approved_on DESC LIMIT ?",
            (ticker.upper(), limit),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "ticker": ticker, "count": 0, "stock_dividends": []}

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "count": len(rows),
            "stock_dividends": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def subscriptions(ticker: str = "", limit: int = 50) -> dict:
    """Query subscription rights for a ticker."""
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT ticker, label, isin_code, approved_on, last_date_prior, percentage, asset_issued, price_unit, subscription_date "
            "FROM subscriptions WHERE ticker=? ORDER BY approved_on DESC LIMIT ?",
            (ticker.upper(), limit),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "ticker": ticker, "count": 0, "subscriptions": []}

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "count": len(rows),
            "subscriptions": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def company_info(ticker: str = "") -> dict:
    """Query company info stored during dividends sync (codeCVM, shares, capital, etc.)."""
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        row = conn.execute(
            "SELECT * FROM company_info WHERE ticker=?",
            (ticker.upper(),),
        ).fetchone()

        if not row:
            return {"status": "not_found", "ticker": ticker}

        return {"status": "ok", "ticker": ticker.upper(), "info": dict(row)}
    finally:
        conn.close()


def status() -> dict:
    """Show sync status for all synced tickers."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced", "message": "Dividends database not found. Run sync first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "Dividends database not found."}

    try:
        cash_total = conn.execute("SELECT COUNT(*) as n FROM cash_dividends").fetchone()["n"]
        stock_total = conn.execute("SELECT COUNT(*) as n FROM stock_dividends").fetchone()["n"]
        sub_total = conn.execute("SELECT COUNT(*) as n FROM subscriptions").fetchone()["n"]

        synced = conn.execute(
            "SELECT * FROM sync_state ORDER BY synced_at DESC"
        ).fetchall()

        return {
            "status": "ok",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "totals": {"cash": cash_total, "stock": stock_total, "subscriptions": sub_total},
            "synced_tickers": [{
                "ticker": r["ticker"],
                "synced_at": r["synced_at"],
                "cash_count": r["cash_count"],
                "stock_count": r["stock_count"],
                "sub_count": r["sub_count"],
            } for r in synced],
        }
    except Exception:
        return {"status": "not_synced", "message": "DB exists but tables not created. Run sync first."}
    finally:
        conn.close()
