"""data_sources/ddm/inflation/query_engine.py -- Read-only queries against inflation.db.

Functions:
  - index_history(slug, limit=60)  - last N observations (ascending by ref_date)
  - last_value(slug)               - latest observation for an index
  - monthly_matrix(slug)           - matrix dict (year x month) for an index
  - search(query, limit=10)        - LIKE search over INDEX_CATALOG
  - summary()                      - catalog overview sorted by (category, slug)

All queries open a read-only SQLite URI connection (fails if DB missing).
"""

from __future__ import annotations

from data_sources.ddm.inflation.catalog import (
    INDEX_CATALOG, connect, db_path,
)
from data_sources.ddm.inflation.fetcher import (
    fetch_index_page, parse_monthly_matrix,
)


def index_history(slug: str = "", limit: int = 60) -> dict:
    """Query historical monthly observations for an index.

    Args:
        slug:  DDM index slug (e.g. 'igp-m').
        limit: Number of most-recent observations to return. Default 60.

    Returns:
        {"status": "ok", "slug": <str>, "name": ..., "count": <int>,
         "observations": [{"ref_date": ..., "month_value": ...,
                           "year_acumulado": ..., "acumulado_12m": ...}, ...]}
    """
    if not slug:
        return {"status": "error", "error": "slug is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = list(reversed(conn.execute(
            "SELECT ref_date, month_value, year_acumulado, acumulado_12m "
            "FROM index_observations WHERE slug=? "
            "ORDER BY ref_date DESC" + (" LIMIT ?" if limit and limit > 0 else ""),
            (slug, limit) if limit and limit > 0 else (slug,),
        ).fetchall()))

        if not rows:
            meta = INDEX_CATALOG.get(slug)
            return {"status": "not_found", "slug": slug,
                    "error": f"No observations for index '{slug}'"
                             + (f" ({meta[0]})" if meta else "")}

        meta = INDEX_CATALOG.get(slug, ("?", "", "", ""))
        return {
            "status": "ok",
            "slug":   slug,
            "name":   meta[0],
            "unit":   meta[3],
            "count":  len(rows),
            "observations": [
                {"ref_date":       r["ref_date"],
                 "month_value":    r["month_value"],
                 "year_acumulado": r["year_acumulado"],
                 "acumulado_12m":  r["acumulado_12m"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def last_value(slug: str = "") -> dict:
    """Get the most recent observation for an index.

    Returns:
        {"status": "ok", "slug": <str>, "name": ..., "unit": ...,
         "ref_date": ..., "month_value": ..., "year_acumulado": ...,
         "acumulado_12m": ...}
    """
    if not slug:
        return {"status": "error", "error": "slug is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        row = conn.execute(
            "SELECT ref_date, month_value, year_acumulado, acumulado_12m "
            "FROM index_observations WHERE slug=? "
            "ORDER BY ref_date DESC LIMIT 1",
            (slug,),
        ).fetchone()
        if not row:
            return {"status": "not_found", "slug": slug,
                    "error": f"No observations for index '{slug}'"}
        meta = INDEX_CATALOG.get(slug, ("?", "", "", ""))
        return {
            "status":        "ok",
            "slug":          slug,
            "name":          meta[0],
            "unit":          meta[3],
            "ref_date":      row["ref_date"],
            "month_value":   row["month_value"],
            "year_acumulado":row["year_acumulado"],
            "acumulado_12m": row["acumulado_12m"],
        }
    finally:
        conn.close()


def monthly_matrix(slug: str = "") -> dict:
    """Get the monthly matrix (year x month) for an index.

    Fetches the live HTML page and parses the matrix table. The matrix is
    NOT stored in the DB (only the historical monthly series is), so this
    mode always makes one HTTP call (5-min cache applies).

    Returns:
        {"status": "ok", "slug": <str>, "name": ...,
         "years": [<int>, ...], "months": ["Jan", ..., "Dez", "Ano"],
         "matrix": {<year_int>: {"Jan": <float|None>, ...}}}
    """
    if not slug:
        return {"status": "error", "error": "slug is required"}
    if slug not in INDEX_CATALOG:
        return {"status": "error", "slug": slug,
                "error": f"Index '{slug}' not in INDEX_CATALOG"}

    page = fetch_index_page(slug, force=False)
    if page.get("status") != "ok":
        return page

    parsed = parse_monthly_matrix(page.get("html", ""))
    meta = INDEX_CATALOG.get(slug, ("?", "", "", ""))
    return {
        "status": "ok",
        "slug":   slug,
        "name":   meta[0],
        "unit":   meta[3],
        "years":  parsed["years"],
        "months": parsed["months"],
        "matrix": parsed["matrix"],
    }


def search(query: str = "", limit: int = 10) -> dict:
    """Search INDEX_CATALOG by name/slug fragment (case-insensitive).

    Returns:
        {"status": "ok", "count": <int>,
         "indices": [{"slug", "name", "category", "unit"}, ...]}
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    q = query.lower()
    matches = []
    for slug, meta in INDEX_CATALOG.items():
        if q in slug.lower() or q in meta[0].lower() or q in meta[2].lower():
            matches.append({
                "slug":     slug,
                "name":     meta[0],
                "category": meta[1],
                "unit":     meta[3],
            })
        if len(matches) >= limit:
            break

    return {"status": "ok", "count": len(matches), "indices": matches}


def summary() -> dict:
    """Catalog overview: every index sorted by (category, slug).

    Returns:
        {"status": "ok", "count": <int>,
         "indices": [{"slug", "name", "category", "description", "unit"}, ...]}
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT slug, name, category, description, unit "
            "FROM index_catalog ORDER BY category, slug"
        ).fetchall()
        if rows:
            return {
                "status":  "ok",
                "count":   len(rows),
                "indices": [dict(r) for r in rows],
            }
    except Exception:
        pass
    finally:
        conn.close()

    # Fallback: in-memory catalog (DB not populated yet).
    indices = [
        {"slug": slug, "name": meta[0], "category": meta[1],
         "description": meta[2], "unit": meta[3]}
        for slug, meta in sorted(INDEX_CATALOG.items(),
                                 key=lambda kv: (kv[1][1], kv[0]))
    ]
    return {"status": "ok", "count": len(indices), "indices": indices}

