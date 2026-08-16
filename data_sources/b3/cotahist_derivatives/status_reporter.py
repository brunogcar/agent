"""data_sources/b3/cotahist_derivatives/status_reporter.py -- DB stats."""
from __future__ import annotations

from data_sources.b3.cotahist_derivatives.catalog import connect


def stats() -> dict:
    """Return summary stats for the cotahist_derivatives table."""
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        total = conn.execute("SELECT COUNT(*) FROM cotahist_derivatives").fetchone()[0]
        underlyings = conn.execute(
            "SELECT COUNT(DISTINCT underlying) FROM cotahist_derivatives"
        ).fetchone()[0]
        dates = conn.execute(
            "SELECT MIN(refdate), MAX(refdate) FROM cotahist_derivatives"
        ).fetchone()
        maturities = conn.execute(
            "SELECT COUNT(DISTINCT maturity) FROM cotahist_derivatives WHERE maturity IS NOT NULL"
        ).fetchone()[0]

        by_type = {}
        for row in conn.execute(
            "SELECT option_type, COUNT(*) as cnt FROM cotahist_derivatives GROUP BY option_type"
        ).fetchall():
            by_type[row["option_type"] or "UNKNOWN"] = row["cnt"]

        return {
            "status": "ok",
            "total_rows": total,
            "underlyings": underlyings,
            "maturities": maturities,
            "date_range": {"from": dates[0], "to": dates[1]},
            "by_type": by_type,
        }
    finally:
        conn.close()
