"""data_sources/b3/index/query_engine.py -- Read B3 index data from local DB.

Query modes:
  index(code)           -- get latest composition of an index
  constituents(code)    -- same as index() (alias)
  search(query)         -- search catalog by name
  summary()             -- overview of all synced indices
  history(code, days)   -- get historical compositions (for tracking changes)
  ticker_search(ticker) -- find which indices a ticker belongs to
"""
from __future__ import annotations

from data_sources.b3.index.catalog import INDEX_CATALOG, connect


def index(index_code: str = "") -> dict:
    """Get the latest composition of an index.

    Args:
        index_code: B3 index code (IBOV, SMLL, etc).

    Returns:
        Dict with index info + constituents list.
    """
    if not index_code:
        return {"status": "error", "error": "index_code is required"}

    conn = connect(read_only=True)
    try:
        cat = conn.execute(
            "SELECT * FROM index_catalog WHERE code = ?", (index_code,)
        ).fetchone()
        if not cat:
            return {"status": "not_found", "error": f"Index {index_code} not in catalog"}

        sync = conn.execute(
            "SELECT * FROM sync_state WHERE index_code = ?", (index_code,)
        ).fetchone()
        if not sync or not sync["last_date"]:
            return {"status": "not_found", "index": index_code,
                    "error": f"No data for index {index_code}. Run sync first."}

        ref_date = sync["last_date"]
        rows = conn.execute(
            """SELECT ticker, company_name, type, theorical_qty,
                      participation, rank, ref_date
               FROM index_constituents
               WHERE index_code = ? AND ref_date = ?
               ORDER BY rank ASC""",
            (index_code, ref_date),
        ).fetchall()

        constituents = [{
            "ticker": r["ticker"],
            "company_name": r["company_name"],
            "type": r["type"],
            "theorical_qty": r["theorical_qty"],
            "participation": r["participation"],
            "rank": r["rank"],
        } for r in rows]

        return {
            "status": "ok",
            "index": index_code,
            "name": cat["name"],
            "description": cat["description"],
            "ref_date": ref_date,
            "constituent_count": len(constituents),
            "constituents": constituents,
            "synced_at": sync["synced_at"],
        }
    finally:
        conn.close()


def search(query: str = "") -> dict:
    """Search the index catalog by name or code.

    Args:
        query: Search string (case-insensitive).
    """
    conn = connect(read_only=True)
    try:
        if not query:
            rows = conn.execute("SELECT * FROM index_catalog ORDER BY code").fetchall()
        else:
            pattern = f"%{query.upper()}%"
            rows = conn.execute(
                """SELECT * FROM index_catalog
                   WHERE code LIKE ? OR name LIKE ? OR description LIKE ?
                   ORDER BY code""",
                (pattern, pattern, pattern),
            ).fetchall()

        return {
            "status": "ok",
            "query": query,
            "count": len(rows),
            "indices": [{
                "code": r["code"],
                "name": r["name"],
                "description": r["description"],
                "active": bool(r["active"]),
            } for r in rows],
        }
    finally:
        conn.close()


def summary() -> dict:
    """Get overview of all synced indices."""
    conn = connect(read_only=True)
    try:
        rows = conn.execute(
            """SELECT c.code, c.name, c.description, c.active,
                      s.last_date, s.row_count, s.synced_at
               FROM index_catalog c
               LEFT JOIN sync_state s ON c.code = s.index_code
               ORDER BY c.active DESC, c.code"""
        ).fetchall()

        return {
            "status": "ok",
            "total_indices": len(rows),
            "active_indices": sum(1 for r in rows if r["active"]),
            "indices": [{
                "code": r["code"],
                "name": r["name"],
                "description": r["description"],
                "active": bool(r["active"]),
                "last_date": r["last_date"] or "",
                "constituent_count": r["row_count"] or 0,
                "synced_at": r["synced_at"] or "",
            } for r in rows],
        }
    finally:
        conn.close()


def history(index_code: str = "", days: int = 90) -> dict:
    """Get historical compositions for tracking index changes over time.

    Args:
        index_code: B3 index code.
        days: Number of days of history to retrieve.

    Returns:
        Dict with list of ref_dates + constituent snapshots.
    """
    if not index_code:
        return {"status": "error", "error": "index_code is required"}

    conn = connect(read_only=True)
    try:
        dates = conn.execute(
            """SELECT DISTINCT ref_date FROM index_constituents
               WHERE index_code = ? AND ref_date >= date('now', ?)
               ORDER BY ref_date DESC""",
            (index_code, f"-{days} days"),
        ).fetchall()

        if not dates:
            return {"status": "not_found", "index": index_code,
                    "error": f"No historical data for {index_code}"}

        snapshots = []
        for d in dates:
            ref_date = d["ref_date"]
            rows = conn.execute(
                """SELECT ticker, company_name, participation, rank
                   FROM index_constituents
                   WHERE index_code = ? AND ref_date = ?
                   ORDER BY rank ASC""",
                (index_code, ref_date),
            ).fetchall()
            snapshots.append({
                "ref_date": ref_date,
                "constituent_count": len(rows),
                "top_10": [{
                    "ticker": r["ticker"],
                    "company_name": r["company_name"],
                    "participation": r["participation"],
                    "rank": r["rank"],
                } for r in rows[:10]],
            })

        return {
            "status": "ok",
            "index": index_code,
            "days": days,
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
        }
    finally:
        conn.close()


def ticker_search(ticker: str = "") -> dict:
    """Find which indices a ticker belongs to.

    Args:
        ticker: B3 ticker (PETR4, VALE3, etc).

    Returns:
        Dict with list of indices the ticker is a constituent of.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    conn = connect(read_only=True)
    try:
        rows = conn.execute(
            """SELECT ic.index_code, cat.name, ic.participation, ic.rank,
                      ic.ref_date, ic.company_name
               FROM index_constituents ic
               JOIN index_catalog cat ON ic.index_code = cat.code
               WHERE ic.ticker = ?
                 AND ic.ref_date = (
                     SELECT MAX(ref_date) FROM index_constituents WHERE index_code = ic.index_code
                 )
               ORDER BY ic.participation DESC""",
            (ticker,),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "ticker": ticker,
                    "error": f"Ticker {ticker} not found in any index"}

        return {
            "status": "ok",
            "ticker": ticker,
            "company_name": rows[0]["company_name"] if rows else "",
            "index_count": len(rows),
            "indices": [{
                "index": r["index_code"],
                "name": r["name"],
                "participation": r["participation"],
                "rank": r["rank"],
                "ref_date": r["ref_date"],
            } for r in rows],
        }
    finally:
        conn.close()
