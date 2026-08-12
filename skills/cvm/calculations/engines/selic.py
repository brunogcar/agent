"""engines/selic.py -- Selic risk-free rate engine.

[v2.0] Switched from series 11 (Selic diária, % a.d.) to series 432
(Meta Selic Copom, % a.a. — already annual). Series 11 was producing
corrupt values (51660% — the BCB API was returning accumulated monthly
values that the compound formula couldn't handle). Series 432 is:
  - Already annual (% a.a.) — no compound annualization needed
  - The actual Copom policy rate (currently ~14.25%)
  - Simple + reliable — values are always 5-45% range
  - No overflow possible

Returns the annualized rate as a PERCENT (% a.a.) for CAPM calculations.

Design decision: We query sgs.db directly (not the BCB API) because:
  1. The data is already synced via data_sources.bcb.sgs.sync_all()
  2. Local SQLite is <1ms vs 200ms HTTP
  3. The sync guard (ensure_fresh) keeps it current

Usage:
    from skills.cvm.calculations.engines.selic import selic_at
    r = selic_at("PETR4", "2024-06-30")  # -> 14.25 (annual % a.a.)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from skills._base import engine_cached  # [v1.8 F7]


# [v2.0] Series 432 = Meta Selic Copom (annual % a.a.)
# Was series 11 (Selic diária % a.d.) — produced corrupt values.
SELIC_SERIES_CODE = 432


def _sgs_db() -> Path:
    """Return path to BCB SGS database.

    Uses the BCB SGS catalog's db_path() directly — single source of truth.
    """
    try:
        from data_sources.bcb.sgs.catalog import db_path as _sgs_db_path
        return _sgs_db_path()
    except Exception:
        return Path.cwd() / "memory_db" / "bcb" / "sgs.db"


def _connect() -> sqlite3.Connection:
    path = _sgs_db()
    if not path.exists():
        raise FileNotFoundError(f"BCB SGS database not found at {path}. Run sync first.")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@engine_cached
def selic_at(company: str, date: str) -> float | None:
    """Get the Selic target rate (Meta Copom) at or before a given date.

    [v2.0] Uses series 432 (Meta Selic Copom, % a.a.) — already annual.
    No compound annualization needed. Values are typically 5-45%.

    Args:
        company: Ticker (unused - Selic is a macro rate, not company-specific).
        date: YYYY-MM-DD.

    Returns:
        Selic rate as a PERCENT (% a.a.), e.g. 14.25 for 14.25%.
        Returns None if SGS DB not synced or no data before date.
    """
    try:
        path = _sgs_db()
        if not path.exists():
            print(f"[selic] sgs.db NOT FOUND at {path} — run bcb.macro dashboard to sync", flush=True)
            return None
        conn = _connect()
        row = conn.execute(
            "SELECT value, ref_date FROM series_observations "
            "WHERE series_code = ? AND ref_date <= ? AND value IS NOT NULL "
            "ORDER BY ref_date DESC LIMIT 1",
            (SELIC_SERIES_CODE, date),
        ).fetchone()
        conn.close()

        if not row or row["value"] is None:
            print(f"[selic] sgs.db exists but series {SELIC_SERIES_CODE} has no data before {date}", flush=True)
            return None

        result = float(row["value"])

        # Sanity check: Brazilian Selic has never exceeded ~45% (2003 peak).
        if result > 50.0 or result < 0.0:
            print(f"[selic] WARNING: value {result}% is out of range (0-50%). Treating as cache miss.", flush=True)
            return None

        return result
    except Exception as e:
        print(f"[selic] ERROR: {type(e).__name__}: {e}", flush=True)
        return None


@engine_cached
def selic_periods(company: str) -> list[dict]:
    """Get all Selic rate periods (for historical charting).

    Returns a list of {"date": ref_date, "selic": annualized_rate} sorted
    oldest-first. Uses monthly sampling (last observation per month) to keep
    the list manageable (~60 points for 5 years).

    [v2.0] Series 432 values are already annual (% a.a.) — return directly.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            """SELECT t.ref_date as ref_date, t.value as value
               FROM series_observations t
               INNER JOIN (
                   SELECT MAX(ref_date) as max_date
                   FROM series_observations
                   WHERE series_code = ? AND value IS NOT NULL
                   GROUP BY substr(ref_date, 1, 7)
               ) m ON t.ref_date = m.max_date
               WHERE t.series_code = ? AND t.value IS NOT NULL
               ORDER BY t.ref_date ASC""",
            (SELIC_SERIES_CODE, SELIC_SERIES_CODE),
        ).fetchall()
        conn.close()

        return [{"date": r["ref_date"], "selic": float(r["value"])}
                for r in rows if r["value"] is not None]
    except (FileNotFoundError, Exception):
        return []


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402
register_engine(EngineSpec(
    name="selic",
    quantity="selic",
    at_fn=selic_at,
    periods_fn=selic_periods,
    source="BCB SGS series 432 (Meta Selic Copom, % a.a.)",
    category="market",
))
