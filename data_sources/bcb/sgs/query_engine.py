"""data_sources/bcb/sgs/query_engine.py -- Read-only queries against sgs.db.

Functions:
  - series(code, days=30, start, end)  - N most recent obs, or windowed range
  - last_value(code)                   - latest observation for a series
  - range_query(code, start, end)      - explicit date window
  - search(query, limit=10)            - LIKE search over series_catalog
  - summary()                          - catalog overview sorted by category

All queries open a read-only SQLite URI connection (fails if DB missing).

[v3] Consistently uses `ref_date` as the field name for observation dates
in all return payloads (was inconsistent in v2 - some used `date`).
"""

from __future__ import annotations

from data_sources.bcb.sgs.catalog import connect, db_path, SERIES_CATALOG


def series(code: int = 0, days: int = 30,
           start: str = "", end: str = "") -> dict:
    """Query observations for a series.

    If `start` + `end` are given, return the windowed range. Otherwise return
    the most recent `days` observations (default 30).

    Args:
        code:  BCB SGS series code (e.g. 11).
        days:  Number of most-recent observations to return. Default 30.
        start: Optional window start (YYYY-MM-DD).
        end:   Optional window end (YYYY-MM-DD).

    Returns:
        {"status": "ok", "code": <int>, "count": <int>,
         "observations": [{"ref_date": ..., "value": ...}, ...]}
    """
    if not code:
        return {"status": "error", "error": "code is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        if start and end:
            rows = conn.execute(
                "SELECT ref_date, value FROM series_observations "
                "WHERE series_code=? AND ref_date >= ? AND ref_date <= ? "
                "ORDER BY ref_date ASC",
                (code, start, end),
            ).fetchall()
        else:
            # Most-recent first, then reverse so caller sees ascending order.
            rows = list(reversed(conn.execute(
                "SELECT ref_date, value FROM series_observations "
                "WHERE series_code=? ORDER BY ref_date DESC LIMIT ?",
                (code, days),
            ).fetchall()))

        if not rows:
            meta = SERIES_CATALOG.get(code)
            return {"status": "not_found", "code": code,
                    "error": f"No observations for series {code}"
                             + (f" ({meta[0]})" if meta else "")}

        return {
            "status": "ok",
            "code": code,
            "name": SERIES_CATALOG.get(code, ("?",))[0],
            "count": len(rows),
            "observations": [{"ref_date": r["ref_date"], "value": r["value"]}
                             for r in rows],
        }
    finally:
        conn.close()


def last_value(code: int = 0) -> dict:
    """Get the most recent observation for a series.

    [v1.3] Now returns ``unit`` + ``name`` from SERIES_CATALOG so callers
    can format the value without a separate catalog lookup.

    Returns:
        {"status": "ok", "code": <int>, "name": ..., "unit": ...,
         "ref_date": ..., "value": ...}
    """
    if not code:
        return {"status": "error", "error": "code is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        row = conn.execute(
            "SELECT ref_date, value FROM series_observations "
            "WHERE series_code=? ORDER BY ref_date DESC LIMIT 1",
            (code,),
        ).fetchone()
        if not row:
            return {"status": "not_found", "code": code,
                    "error": f"No observations for series {code}"}
        meta = SERIES_CATALOG.get(code, ("?", "", "", "", ""))
        return {
            "status": "ok",
            "code": code,
            "name": meta[0],
            "unit": meta[2],
            "ref_date": row["ref_date"],
            "value": row["value"],
        }
    finally:
        conn.close()


def range_query(code: int = 0, start: str = "", end: str = "") -> dict:
    """Query observations for a series in an explicit date window."""
    if not code:
        return {"status": "error", "error": "code is required"}
    if not start or not end:
        return {"status": "error", "code": code,
                "error": "start and end (YYYY-MM-DD) are required"}
    return series(code=code, start=start, end=end)


def search(query: str = "", limit: int = 10) -> dict:
    """Search the series catalog by name fragment (case-insensitive).

    Returns:
        {"status": "ok", "count": <int>,
         "series": [{"code", "name", "frequency", "unit", "category"}, ...]}
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT code, name, frequency, unit, category "
            "FROM series_catalog WHERE name LIKE ? "
            "ORDER BY category, code LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return {
            "status": "ok",
            "count": len(rows),
            "series": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def summary() -> dict:
    """Catalog overview: every series sorted by (category, code).

    Returns:
        {"status": "ok", "count": <int>,
         "series": [{"code", "name", "frequency", "unit", "category"}, ...]}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT code, name, frequency, unit, category "
            "FROM series_catalog ORDER BY category, code"
        ).fetchall()
        return {
            "status": "ok",
            "count": len(rows),
            "series": [dict(r) for r in rows],
        }
    finally:
        conn.close()
