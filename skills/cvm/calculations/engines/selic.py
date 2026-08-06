"""engines/selic.py -- Selic risk-free rate engine.

Fetches the Selic daily rate from BCB SGS (series 11, already synced in
sgs.db). Returns the ANNUALIZED rate (% a.a.) for CAPM calculations.

The BCB SGS series 11 is a DAILY rate (% a.d., base 252). This engine
annualizes it: rate_a.a. = rate_a.d. * 252.

Design decision: We query sgs.db directly (not the BCB API) because:
  1. The data is already synced via data_sources.bcb.sgs.sync_all()
  2. Local SQLite is <1ms vs 200ms HTTP
  3. The sync guard (ensure_fresh) keeps it current

Usage:
    from skills.cvm.calculations.engines.selic import selic_at
    r = selic_at("PETR4", "2024-06-30")  # -> 10.40 (annualized % a.a.)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from skills._base import engine_cached  # [v1.8 F7]


def _sgs_db() -> Path:
    """Return path to BCB SGS database."""
    try:
        from data_sources.cvm._db import cvm_db_path
        return cvm_db_path().parent / "bcb" / "sgs.db"
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
    """Get the annualized Selic rate at or before a given date.

    Args:
        company: Ticker (unused - Selic is a macro rate, not company-specific.
                 Accepted for API consistency with other engines).
        date: YYYY-MM-DD.

    Returns:
        Annualized Selic rate as a PERCENT (% a.a.), e.g. 10.40 for 10.40%.
        Returns None if SGS DB not synced or no data before date.
    """
    try:
        conn = _connect()
        # Series 11 = Selic daily rate (% a.d., base 252)
        row = conn.execute(
            "SELECT value FROM series_observations "
            "WHERE series_code = 11 AND ref_date <= ? AND value IS NOT NULL "
            "ORDER BY ref_date DESC LIMIT 1",
            (date,),
        ).fetchone()
        conn.close()

        if not row or row["value"] is None:
            return None

        # Annualize: compound (geometric) annualization on base 252.
        # [new commit] Was simple multiplication (daily_rate * 252), which
        # underestimates the annual rate. BCB series 11 is the daily accrued
        # rate (% a.d.) — the correct annualization is compound:
        #   annual = ((1 + daily/100)^252 - 1) * 100
        # Example: daily=0.041% → simple=10.33% → compound=10.88% (55bps diff).
        # Found by external LLM review (Qwen). O(1) math, no perf impact.
        daily_rate = float(row["value"])
        daily_frac = daily_rate / 100.0
        annual_frac = (1.0 + daily_frac) ** 252 - 1.0
        return annual_frac * 100.0
    except Exception:
        return None


@engine_cached
def selic_periods(company: str) -> list[dict]:
    """Get all Selic rate periods (for historical charting).

    Returns a list of {"date": ref_date, "selic": annualized_rate} sorted
    oldest-first. Uses monthly sampling (last observation per month) to keep
    the list manageable (~60 points for 5 years).
    """
    try:
        conn = _connect()
        rows = conn.execute(
            """SELECT MAX(ref_date) as ref_date, MAX(value) as value
               FROM series_observations
               WHERE series_code = 11 AND value IS NOT NULL
               GROUP BY substr(ref_date, 1, 7)
               ORDER BY ref_date ASC""",
        ).fetchall()
        conn.close()

        return [{"date": r["ref_date"], "selic": float(r["value"]) * 252.0}
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
    source="BCB SGS series 11 (Selic diaria, base 252) -> annualized",
    category="market",
))
