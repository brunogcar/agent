"""data_sources/ddm/focus/query_engine.py -- Read-only queries against focus.db.

Functions:
  - focus_by_year(year)           - all indicators for a given year (latest sync)
  - focus_by_indicator(indicator) - all years for a given indicator (latest sync)
  - last_value()                  - latest sync metadata + all observations
  - search(query)                 - LIKE search by indicator name
  - summary()                     - overview stats (years, indicators, last sync)
  - all_data()                    - all observations (latest sync)
  - focus_history(indicator, year) - [W6] all ref_dates for an indicator+year combo

All queries open a read-only SQLite URI connection (fails if DB missing).
Each query targets only the latest ref_date by default so callers see the
current Focus bulletin. Historical ref_dates are preserved in the DB for
future time-series features.

[v2] Values are now stored as REAL (float). The _row_to_dict returns floats
directly — no display-layer parsing needed. The skills/ddm/focus/helpers.py
parse_numeric() is still used for backwards compatibility (handles both
float and string inputs).
"""

from __future__ import annotations

from data_sources.ddm.focus.catalog import (
    connect, db_path,
)


def _latest_ref_date(conn) -> str:
    """Return the most recent ref_date in focus_observations, or ""."""
    row = conn.execute(
        "SELECT MAX(ref_date) as d FROM focus_observations"
    ).fetchone()
    return row["d"] if row and row["d"] else ""


def _row_to_dict(row) -> dict:
    return {
        "year":           row["year"],
        "indicator":      row["indicator"],
        "four_weeks_ago": row["four_weeks_ago"],
        "one_week_ago":   row["one_week_ago"],
        "today":          row["today"],
        "comparison":     row["comparison"],
        "respondents":    row["respondents"],
        "ref_date":       row["ref_date"],
        "synced_at":      row["synced_at"],
    }


def focus_by_year(year: int = 0) -> dict:
    """Query all indicators for a given year (latest sync only).

    Args:
        year: 4-digit target year (e.g. 2026). Required.

    Returns:
        {"status": "ok", "year": <int>, "ref_date": <str>,
         "count": <int>, "observations": [<dict>, ...]}
    """
    if not year:
        return {"status": "error", "error": "year is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        ref_date = _latest_ref_date(conn)
        if not ref_date:
            return {"status": "not_found", "year": year,
                    "error": "No observations in DB. Run sync_all first."}
        rows = list(conn.execute(
            "SELECT year, indicator, four_weeks_ago, one_week_ago, today, "
            "comparison, respondents, ref_date, synced_at "
            "FROM focus_observations WHERE year=? AND ref_date=? "
            "ORDER BY indicator ASC",
            (year, ref_date),
        ).fetchall())
        if not rows:
            return {"status": "not_found", "year": year, "ref_date": ref_date,
                    "error": f"No observations for year {year}"}
        return {
            "status":      "ok",
            "year":        year,
            "ref_date":    ref_date,
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def focus_by_indicator(indicator: str = "") -> dict:
    """Query all years for a given indicator (latest sync only).

    Args:
        indicator: Indicator name (e.g. "IPCA"). Required. Case-insensitive
                   match against the stored value (DDM uses Title Case).

    Returns:
        {"status": "ok", "indicator": <str>, "ref_date": <str>,
         "count": <int>, "observations": [<dict>, ...]}
    """
    if not indicator:
        return {"status": "error", "error": "indicator is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        ref_date = _latest_ref_date(conn)
        if not ref_date:
            return {"status": "not_found", "indicator": indicator,
                    "error": "No observations in DB. Run sync_all first."}
        rows = list(conn.execute(
            "SELECT year, indicator, four_weeks_ago, one_week_ago, today, "
            "comparison, respondents, ref_date, synced_at "
            "FROM focus_observations "
            "WHERE indicator=? COLLATE NOCASE AND ref_date=? "
            "ORDER BY year ASC",
            (indicator, ref_date),
        ).fetchall())
        if not rows:
            return {"status": "not_found", "indicator": indicator,
                    "ref_date": ref_date,
                    "error": f"No observations for indicator '{indicator}'"}
        return {
            "status":      "ok",
            "indicator":   rows[0]["indicator"],
            "ref_date":    ref_date,
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def last_value() -> dict:
    """Get the latest sync metadata + all observations for the latest ref_date.

    Returns:
        {"status": "ok", "ref_date": <str>, "synced_at": <iso>,
         "count": <int>, "observations": [<dict>, ...]}
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
        rows = list(conn.execute(
            "SELECT year, indicator, four_weeks_ago, one_week_ago, today, "
            "comparison, respondents, ref_date, synced_at "
            "FROM focus_observations WHERE ref_date=? "
            "ORDER BY year ASC, indicator ASC",
            (ref_date,),
        ).fetchall())
        sync_row = conn.execute(
            "SELECT synced_at FROM sync_state WHERE slug='focus'"
        ).fetchone()
        return {
            "status":      "ok",
            "ref_date":    ref_date,
            "synced_at":   sync_row["synced_at"] if sync_row else "",
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def search(query: str = "", limit: int = 50) -> dict:
    """Search observations by indicator name fragment (case-insensitive LIKE).

    Searches the latest ref_date only. Returns distinct (year, indicator)
    combinations matching the query, sorted by indicator name.

    Returns:
        {"status": "ok", "count": <int>,
         "observations": [<dict>, ...]}
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        ref_date = _latest_ref_date(conn)
        if not ref_date:
            return {"status": "not_found",
                    "error": "No observations in DB. Run sync_all first."}
        pattern = f"%{query}%"
        sql = (
            "SELECT year, indicator, four_weeks_ago, one_week_ago, today, "
            "comparison, respondents, ref_date, synced_at "
            "FROM focus_observations "
            "WHERE ref_date=? AND indicator LIKE ? COLLATE NOCASE "
            "ORDER BY indicator ASC, year ASC"
        )
        params = (ref_date, pattern)
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (ref_date, pattern, limit)
        rows = list(conn.execute(sql, params).fetchall())
        return {
            "status":      "ok",
            "ref_date":    ref_date,
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


def summary() -> dict:
    """Overview stats: years covered, distinct indicators, last sync.

    Returns:
        {"status": "ok", "ref_date": <str>, "synced_at": <iso>,
         "years": [<int>, ...], "indicators": [<str>, ...],
         "year_count": <int>, "indicator_count": <int>,
         "row_count": <int>}
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
        year_rows = conn.execute(
            "SELECT DISTINCT year FROM focus_observations "
            "WHERE ref_date=? ORDER BY year ASC",
            (ref_date,),
        ).fetchall()
        ind_rows = conn.execute(
            "SELECT DISTINCT indicator FROM focus_observations "
            "WHERE ref_date=? ORDER BY indicator ASC",
            (ref_date,),
        ).fetchall()
        count_row = conn.execute(
            "SELECT COUNT(*) as n FROM focus_observations WHERE ref_date=?",
            (ref_date,),
        ).fetchone()
        sync_row = conn.execute(
            "SELECT synced_at FROM sync_state WHERE slug='focus'"
        ).fetchone()
        years = [r["year"] for r in year_rows]
        indicators = [r["indicator"] for r in ind_rows]
        return {
            "status":          "ok",
            "ref_date":        ref_date,
            "synced_at":       sync_row["synced_at"] if sync_row else "",
            "years":           years,
            "indicators":      indicators,
            "year_count":      len(years),
            "indicator_count": len(indicators),
            "row_count":       count_row["n"] if count_row else 0,
        }
    finally:
        conn.close()


def all_data() -> dict:
    """Return all observations for the latest ref_date (full snapshot).

    Returns:
        {"status": "ok", "ref_date": <str>, "synced_at": <iso>,
         "count": <int>, "observations": [<dict>, ...]}

    Rows are sorted by year ASC then indicator ASC so the dashboard can
    iterate year-by-year and render one table per year.
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
        rows = list(conn.execute(
            "SELECT year, indicator, four_weeks_ago, one_week_ago, today, "
            "comparison, respondents, ref_date, synced_at "
            "FROM focus_observations WHERE ref_date=? "
            "ORDER BY year ASC, indicator ASC",
            (ref_date,),
        ).fetchall())
        sync_row = conn.execute(
            "SELECT synced_at FROM sync_state WHERE slug='focus'"
        ).fetchone()
        return {
            "status":      "ok",
            "ref_date":    ref_date,
            "synced_at":   sync_row["synced_at"] if sync_row else "",
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()



def focus_history(indicator: str = "", year: int = 0, limit: int = 0) -> dict:
    """[W6] Query all historical ref_dates for an indicator + year combo.

    Unlike the other query functions (which filter `WHERE ref_date = ?` to
    the latest sync only), this returns ALL ref_dates stored in the DB for
    the given (indicator, year) pair. This exposes the historical snapshot
    series that sync accumulates over time.

    Args:
        indicator: Indicator name (e.g. "IPCA"). Required. Case-insensitive.
        year:      4-digit target year (e.g. 2026). Required.
        limit:     Max rows. 0 = all. Default: 0.

    Returns:
        {"status": "ok", "indicator": <str>, "year": <int>,
         "count": <int>, "observations": [<dict>, ...]}
        Observations are sorted by ref_date ASC (oldest first) so charts
        can plot the expectation evolution over time.
    """
    if not indicator:
        return {"status": "error", "error": "indicator is required"}
    if not year:
        return {"status": "error", "error": "year is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        sql = (
            "SELECT year, indicator, four_weeks_ago, one_week_ago, today, "
            "comparison, respondents, ref_date, synced_at "
            "FROM focus_observations "
            "WHERE indicator=? COLLATE NOCASE AND year=? "
            "ORDER BY ref_date ASC"
        )
        params: tuple = (indicator, year)
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (indicator, year, limit)
        rows = list(conn.execute(sql, params).fetchall())
        if not rows:
            return {"status": "not_found", "indicator": indicator,
                    "year": year,
                    "error": f"No historical observations for {indicator} {year}"}
        return {
            "status":      "ok",
            "indicator":   rows[0]["indicator"],
            "year":        year,
            "count":       len(rows),
            "observations": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()
