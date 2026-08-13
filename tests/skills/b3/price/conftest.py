"""Shared fixtures for the b3.price skill tests.

Builds a synthetic cotahist.db with 10 trading days of PETR4 OHLCV data and
monkeypatches the engines._cotahist_db + engines._connect paths so the skill
reads only from the synthetic DB. No real DB, no network, fast tests.

Env vars (PLANNER_MODEL etc.) are inherited from parent conftest files; we
also set CVM_SKIP_SYNC=1 + CVM_SKIP_HTML=1 here so route() doesn't trigger
sync or HTML generation.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date as _date, timedelta as _timedelta
from pathlib import Path

import pytest

# Set env vars at module level (before any test or core.config import).
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
# Skip sync guard + HTML auto-generation in tests.
os.environ.setdefault("CVM_SKIP_SYNC", "1")
os.environ.setdefault("CVM_SKIP_HTML", "1")


# ── Synthetic cotahist.db builder ────────────────────────────────────────────

def _make_cotahist_db(tmp_path: Path, ticker: str = "PETR4") -> Path:
    """Create a synthetic cotahist.db with 10 trading days of OHLCV data.

    Uses the same SCHEMA_SQL as data_sources.b3.cotahist.catalog to ensure
    engine queries match the production schema. Prices drift upward to
    produce a non-zero cumulative return; volumes vary; some days have
    close >= open (up day) and some have close < open (down day).
    """
    from data_sources.b3.cotahist.catalog import SCHEMA_SQL

    db_path = tmp_path / "cotahist.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL.replace("DROP TABLE IF EXISTS cotahist;\n", ""))

    # Generate 10 business days (skipping weekends) ending today.
    base_date = _date(2024, 1, 2)  # Tuesday Jan 2, 2024
    business_days: list[_date] = []
    d = base_date
    while len(business_days) < 10:
        if d.weekday() < 5:  # Mon-Fri
            business_days.append(d)
        d += _timedelta(days=1)

    # Synthetic prices: start at R$ 38.00, drift up with some volatility,
    # mix of up/down days so crossovers + colors get exercised.
    prices = [
        # (open, high, low, close, volume, trade_count)
        (38.00, 38.50, 37.80, 38.20, 100_000_000, 15000),  # up day
        (38.20, 38.70, 38.10, 38.60,  95_000_000, 14000),  # up day
        (38.60, 38.80, 38.20, 38.30, 110_000_000, 16000),  # down day
        (38.30, 38.90, 38.20, 38.80, 120_000_000, 17000),  # up day
        (38.80, 39.20, 38.70, 39.10, 130_000_000, 18000),  # up day
        (39.10, 39.30, 38.80, 38.90,  85_000_000, 13000),  # down day
        (38.90, 39.50, 38.85, 39.40, 140_000_000, 19000),  # up day
        (39.40, 39.80, 39.30, 39.70, 125_000_000, 17500),  # up day
        (39.70, 40.00, 39.50, 39.60,  90_000_000, 13500),  # down day
        (39.60, 40.20, 39.55, 40.10, 150_000_000, 20000),  # up day (latest)
    ]

    for d, (o, h, l, c, vol, trades) in zip(business_days, prices):
        conn.execute(
            """INSERT INTO cotahist
               (regtype, refdate, symbol, bdi_code, market_type, corp_name,
                spec_code, days_settle, currency, open, high, low, average,
                close, best_bid, best_ask, trade_count, contracts, volume,
                strike, strike_adj, maturity, lot_size, strike_pts, isin, dist_id, _ingested_at)
               VALUES ('01', ?, ?, 2, 10, 'PETROLEO BRASILEIRO S.A.',
                       'PN', 0, 'R$', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '', '', 100, NULL, 'BRPETRACNPR6', 0, '2024-01-15')""",
            (d.isoformat(), ticker, o, h, l, c, c, c, c, trades, int(vol / c), vol),
        )

    # Insert a sync_state row so freshness checks succeed if they ever run.
    conn.execute(
        "INSERT INTO sync_state (year, synced_at, rows_added, duration_s) "
        "VALUES (2024, '2024-01-15T00:00:00', 10, 0.1)"
    )
    conn.commit()
    conn.close()
    return db_path


# ── Pytest fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def price_env(tmp_path: Path, monkeypatch):
    """Set up synthetic cotahist.db + patch engine paths.

    Patches:
      - ``skills.b3.price.engines._cotahist_db`` → synthetic db_path
      - ``skills.b3.price.engines._connect``      → sqlite3 connection to it

    Returns the Path to the synthetic cotahist.db.
    """
    db_path = _make_cotahist_db(tmp_path)

    def mock_connect():
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("skills.b3.price.engines._cotahist_db", lambda: db_path)
    monkeypatch.setattr("skills.b3.price.engines._connect", mock_connect)
    return db_path
