"""data_sources/ddm/fluxo/query_engine.py -- Read-only queries against fluxo.db.

Functions:
  - fluxo_data(limit=0)              - all observations (ascending by date)
  - fluxo_by_investor(investor, limit=0)
                                     - date + one investor column
  - last_value()                     - latest observation
  - by_date(date)                    - one observation by date
                                       (YYYY-MM-DD or DD/MM/YYYY accepted)
  - search(query, limit=50)          - LIKE search by date prefix
  - summary()                        - overview stats (row count, date range)
  - monthly_cumulative(investor)     - group by month, sum daily values
  - annual_cumulative(investor)      - running cumulative sum (each day =
                                       previous + today)

All queries open a read-only SQLite URI connection (fails if DB missing).
"""

from __future__ import annotations

from data_sources.ddm.fluxo.catalog import (
    connect, db_path,
)


# Map investor display names to DB column names. The /fluxo page uses PT-BR
# labels ("Estrangeiro", "Institucional", "Pessoa física", "Inst.
# Financeira", "Outros") but the DB schema uses ASCII column names
# ("estrangeiro", "institucional", "pessoa_fisica", "inst_financeira",
# "outros") to avoid SQLite identifier-quoting headaches.
INVESTOR_COLUMNS: dict[str, str] = {
    "estrangeiro":     "estrangeiro",
    "institucional":   "institucional",
    "pessoa_fisica":   "pessoa_fisica",
    "pessoa fisica":   "pessoa_fisica",
    "inst_financeira": "inst_financeira",
    "inst financeira": "inst_financeira",
    "outros":          "outros",
}


def _normalize_investor(investor: str) -> str:
    """Map an investor label to its DB column name (case-insensitive).

    Accepts both the canonical column name ("estrangeiro") and the PT-BR
    label ("Pessoa física" -> "pessoa_fisica"). Raises ValueError if the
    investor is unknown.
    """
    if not investor:
        raise ValueError("investor is required")
    key = investor.strip().lower()
    if key not in INVESTOR_COLUMNS:
        raise ValueError(
            f"Unknown investor '{investor}'. "
            f"Valid: {sorted(set(INVESTOR_COLUMNS.values()))}"
        )
    return INVESTOR_COLUMNS[key]


def _row_to_dict(row) -> dict:
    return {
        "ref_date":        row["ref_date"],
        "estrangeiro":     row["estrangeiro"],
        "institucional":   row["institucional"],
        "pessoa_fisica":   row["pessoa_fisica"],
        "inst_financeira": row["inst_financeira"],
        "outros":          row["outros"],
        "synced_at":       row["synced_at"],
    }


def _normalize_date_input(s: str) -> str:
    """Accept either YYYY-MM-DD or DD/MM/YYYY; return YYYY-MM-DD.

    Returns "" for empty / unparseable input.
    """
    if not s:
        return ""
    s = s.strip()
    # Already ISO YYYY-MM-DD?
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    # PT-BR DD/MM/YYYY?
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        d, mo, y = s.split("/")
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except (ValueError, TypeError):
            return ""
    return ""


def _latest_ref_date(conn) -> str:
    """Return the most recent ref_date in fluxo_observations, or ""."""
    row = conn.execute(
        "SELECT MAX(ref_date) as d FROM fluxo_observations"
    ).fetchone()
    return row["d"] if row and row["d"] else ""


def fluxo_data(limit: int = 0) -> dict:
    """Get all observations (daily data, ascending by date).

    Args:
        limit: Max results. Default 0 = all.

    Returns:
        {"status": "ok", "count": <int>, "observations": [<dict>, ...]}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        sql = (
            "SELECT ref_date, estrangeiro, institucional, pessoa_fisica, "
            "inst_financeira, outros, synced_at "
            "FROM fluxo_observations "
            "ORDER BY ref_date ASC"
        )
        params: tuple = ()
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (limit,)
        rows = list(conn.execute(sql, params).fetchall())
        sync_row = conn.execute(
            "SELECT synced_at FROM sync_state WHERE slug='fluxo'"
        ).fetchone()
        return {
            "status":      "ok",
            "count":       len(rows),
            "synced_at":   sync_row["synced_at"] if sync_row else "",
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def fluxo_by_investor(investor: str = "", limit: int = 0) -> dict:
    """Get date + one investor column (ascending by date).

    Args:
        investor: Investor name (e.g. "estrangeiro" or "Pessoa física").
        limit:    Max results. Default 0 = all.

    Returns:
        {"status": "ok", "investor": <str>, "count": <int>,
         "observations": [{"ref_date": ..., "value": <float>}, ...]}
    """
    try:
        col = _normalize_investor(investor)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        sql = (
            f"SELECT ref_date, {col} as value "
            f"FROM fluxo_observations "
            f"ORDER BY ref_date ASC"
        )
        params: tuple = ()
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (limit,)
        rows = list(conn.execute(sql, params).fetchall())
        return {
            "status":      "ok",
            "investor":    col,
            "count":       len(rows),
            "observations": [
                {"ref_date": r["ref_date"], "value": r["value"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def last_value() -> dict:
    """Get the latest observation (most recent ref_date).

    Returns:
        {"status": "ok", "ref_date": <str>, "synced_at": <iso>,
         "observation": <dict>}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        ref_date = _latest_ref_date(conn)
        if not ref_date:
            return {"status": "not_found",
                    "error": "No observations in DB. Run sync_all first."}
        row = conn.execute(
            "SELECT ref_date, estrangeiro, institucional, pessoa_fisica, "
            "inst_financeira, outros, synced_at "
            "FROM fluxo_observations WHERE ref_date=?",
            (ref_date,),
        ).fetchone()
        sync_row = conn.execute(
            "SELECT synced_at FROM sync_state WHERE slug='fluxo'"
        ).fetchone()
        return {
            "status":      "ok",
            "ref_date":    ref_date,
            "synced_at":   sync_row["synced_at"] if sync_row else "",
            "observation": _row_to_dict(row) if row else None,
        }
    finally:
        conn.close()


def by_date(ticker: str = "") -> dict:
    """Get one observation by date.

    Args:
        ticker: Date string. Accepts either YYYY-MM-DD or DD/MM/YYYY.
                (Named "ticker" for API parity with the other DDM modes;
                in this sub-domain the "ticker" slot is a date.)

    Returns:
        {"status": "ok", "ref_date": <str>, "observation": <dict>}
    """
    if not ticker:
        return {"status": "error", "error": "ticker (date) is required"}
    ref_date = _normalize_date_input(ticker)
    if not ref_date:
        return {"status": "error",
                "error": f"Invalid date '{ticker}'. Use YYYY-MM-DD or DD/MM/YYYY."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        row = conn.execute(
            "SELECT ref_date, estrangeiro, institucional, pessoa_fisica, "
            "inst_financeira, outros, synced_at "
            "FROM fluxo_observations WHERE ref_date=?",
            (ref_date,),
        ).fetchone()
        if not row:
            return {"status": "not_found", "ref_date": ref_date,
                    "error": f"No observation for {ref_date}"}
        return {
            "status":      "ok",
            "ref_date":    ref_date,
            "observation": _row_to_dict(row),
        }
    finally:
        conn.close()


def search(query: str = "", limit: int = 50) -> dict:
    """Search observations by date fragment (LIKE prefix match).

    Args:
        query: Date fragment (e.g. "2026-08" -> all August 2026 days).
        limit: Max results. Default 50.

    Returns:
        {"status": "ok", "count": <int>, "observations": [<dict>, ...]}

    Rows are sorted by ref_date DESC (newest first) so users see the
    most recent matching days first.
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # Accept either YYYY-MM-DD or DD/MM/YYYY input -> normalize to
        # YYYY-MM-DD before LIKE matching.
        normalized = _normalize_date_input(query)
        pattern_str = normalized if normalized else query
        pattern = f"{pattern_str}%"
        sql = (
            "SELECT ref_date, estrangeiro, institucional, pessoa_fisica, "
            "inst_financeira, outros, synced_at "
            "FROM fluxo_observations "
            "WHERE ref_date LIKE ? "
            "ORDER BY ref_date DESC"
        )
        params: tuple = (pattern,)
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (pattern, limit)
        rows = list(conn.execute(sql, params).fetchall())
        return {
            "status":      "ok",
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def summary() -> dict:
    """Overview stats: row count, date range, last sync.

    Returns:
        {"status": "ok", "row_count": <int>, "first_date": <str>,
         "last_date": <str>, "synced_at": <iso>}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        count_row = conn.execute(
            "SELECT COUNT(*) as n FROM fluxo_observations"
        ).fetchone()
        range_row = conn.execute(
            "SELECT MIN(ref_date) as first_date, MAX(ref_date) as last_date "
            "FROM fluxo_observations"
        ).fetchone()
        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='fluxo'"
        ).fetchone()
        return {
            "status":      "ok",
            "row_count":   count_row["n"] if count_row else 0,
            "first_date":  range_row["first_date"] if range_row else "",
            "last_date":   (sync_row["last_date"] if sync_row else
                            (range_row["last_date"] if range_row else "")),
            "synced_at":   sync_row["synced_at"] if sync_row else "",
            "sync_rows":   sync_row["row_count"] if sync_row else 0,
        }
    finally:
        conn.close()


def monthly_cumulative(investor: str = "") -> dict:
    """Group observations by month, sum daily values -> monthly cumulative.

    Each month's value = sum of all daily values in that month. Useful
    for "how much did estrangeiro flow into B3 in August 2026?".

    Args:
        investor: Investor name (e.g. "estrangeiro" or "Pessoa física").

    Returns:
        {"status": "ok", "investor": <str>, "count": <int>,
         "observations": [{"month": "2026-08", "label": "Ago/2026",
                           "value": <float>}, ...]}

    Months are sorted ASC (oldest first). Labels use PT-BR month
    abbreviations (Jan/Fev/Mar/Abr/Mai/Jun/Jul/Ago/Set/Out/Nov/Dez).
    """
    try:
        col = _normalize_investor(investor)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # Group by YYYY-MM (first 7 chars of ref_date), sum the investor col.
        rows = list(conn.execute(
            f"SELECT SUBSTR(ref_date, 1, 7) as month, "
            f"       SUM({col}) as value "
            f"FROM fluxo_observations "
            f"WHERE {col} IS NOT NULL "
            f"GROUP BY SUBSTR(ref_date, 1, 7) "
            f"ORDER BY month ASC",
        ).fetchall())
        return {
            "status":      "ok",
            "investor":    col,
            "count":       len(rows),
            "observations": [
                {"month": r["month"],
                 "label": _month_label(r["month"]),
                 "value": r["value"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def annual_cumulative(investor: str = "") -> dict:
    """Year-to-date running cumulative: resets on January 1st each year.

    Produces a daily series where each value is the running total of the
    investor's flow from January 1st of that year to the current day.
    Resets to zero at each year boundary (sawtooth pattern).

    [v2 fix B9] Previously this was a continuous running sum from the first
    day in the DB (since-inception), not year-to-date. The tab is labeled
    "Anual" / "Acumulado anual" which means YTD. See review B9/W1.

    Args:
        investor: Investor name (e.g. "estrangeiro" or "Pessoa física").

    Returns:
        {"status": "ok", "investor": <str>, "count": <int>,
         "observations": [{"ref_date": <str>, "value": <float>}, ...]}

    Sorted ASC by date (oldest first). Days with NULL values are skipped
    (the running sum does not advance on those days).
    """
    try:
        col = _normalize_investor(investor)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = list(conn.execute(
            f"SELECT ref_date, {col} as value "
            f"FROM fluxo_observations "
            f"WHERE {col} IS NOT NULL "
            f"ORDER BY ref_date ASC",
        ).fetchall())
        result: list[dict] = []
        running = 0.0
        current_year = ""
        for r in rows:
            v = r["value"]
            if v is None:
                continue
            # [v2 fix B9] Reset the running sum on year boundary.
            year = r["ref_date"][:4]
            if year != current_year:
                running = 0.0
                current_year = year
            running += v
            result.append({"ref_date": r["ref_date"], "value": running})
        return {
            "status":      "ok",
            "investor":    col,
            "count":       len(result),
            "observations": result,
        }
    finally:
        conn.close()


_PT_BR_MONTHS = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


def _month_label(month: str) -> str:
    """Convert "2026-08" -> "Ago/2026" (PT-BR month abbreviation)."""
    if not month or len(month) < 7:
        return month or ""
    try:
        y = month[0:4]
        mo = int(month[5:7])
        if 1 <= mo <= 12:
            return f"{_PT_BR_MONTHS[mo - 1]}/{y}"
    except (ValueError, TypeError):
        pass
    return month

