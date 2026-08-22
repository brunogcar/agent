"""engines/price.py — COTAHIST daily close price engine.

Standalone module: importable by historical skill + future backtest skill.
Queries cotahist.db directly for maximum performance.

Usage:
    from skills.cvm.calculations.engines.price import price_at, price_series
    p = price_at("PETR4", "2024-06-30")      # → 38.50
    s = price_series("PETR4", "2024-01-01", "2024-12-31")  # → [{date, close}, ...]
"""
# Color scheme: skills/_colors/price.py — 22 ranges (red → green → blue gradient)

from __future__ import annotations

import sqlite3
from pathlib import Path
from skills._base import engine_cached  # [v1.8 F7]


def _cotahist_db() -> Path:
    """Return the path to cotahist.db.

    CVM DBs are at memory_db/cvm/ (cvm_db_path()).
    B3 DBs are at memory_db/b3/ — one level up from cvm/, then into b3/.
    So: cvm_db_path().parent / "b3" / "cotahist.db"
    """
    from data_sources.cvm._db import cvm_db_path
    return cvm_db_path().parent / "b3" / "cotahist.db"


def _connect() -> sqlite3.Connection:
    path = _cotahist_db()
    if not path.exists():
        raise FileNotFoundError(f"COTAHIST database not found at {path}. Run sync first.")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@engine_cached
def price_at(ticker: str, date: str) -> float | None:
    """Get close price on a specific date (or nearest trading day <= date).

    Args:
        ticker: B3 ticker (PETR4).
        date: YYYY-MM-DD.

    Returns:
        Close price as float, or None if no data.
    """
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT close FROM cotahist "
            "WHERE symbol = ? AND refdate <= ? AND market_type = 10 "
            "AND close IS NOT NULL AND close > 0 "
            "ORDER BY refdate DESC LIMIT 1",
            (ticker.strip().upper(), date),
        ).fetchone()
        conn.close()
        return float(row["close"]) if row and row["close"] else None
    except (FileNotFoundError, Exception):
        return None


@engine_cached
def price_series(ticker: str, date_from: str, date_to: str) -> list[dict]:
    """Get daily close prices for a date range.

    Args:
        ticker: B3 ticker (PETR4).
        date_from: YYYY-MM-DD.
        date_to: YYYY-MM-DD.

    Returns:
        List of {"date": "YYYY-MM-DD", "close": float} sorted oldest-first.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT refdate, close FROM cotahist "
            "WHERE symbol = ? AND refdate >= ? AND refdate <= ? AND market_type = 10 "
            "AND close IS NOT NULL AND close > 0 "
            "ORDER BY refdate ASC",
            (ticker.strip().upper(), date_from, date_to),
        ).fetchall()
        conn.close()
        return [{"date": r["refdate"], "close": float(r["close"])} for r in rows]
    except (FileNotFoundError, Exception):
        return []


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="price",
    quantity="close",
    at_fn=price_at,
    periods_fn=price_series,
    source="COTAHIST (B3 daily OHLCV, 2010+)",
    category="market",
))
