"""Shared fixtures for the b3.options skill tests.

Builds a synthetic cotahist.db with both the cotahist (equities) and
cotahist_derivatives (options) tables populated with sample PETR options data.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
os.environ.setdefault("CVM_SKIP_SYNC", "1")
os.environ.setdefault("CVM_SKIP_HTML", "1")


def _make_derivatives_db(tmp_path: Path) -> Path:
    """Create a synthetic cotahist.db with cotahist_derivatives table."""
    from data_sources.b3.cotahist_derivatives.catalog import DERIVATIVES_SCHEMA_SQL

    db_path = tmp_path / "cotahist.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(DERIVATIVES_SCHEMA_SQL)

    # Insert sample PETR options (calls + puts) for a single day.
    sample_date = "2026-01-15"
    maturity = "2026-08-17"
    samples = [
        # (symbol, bdi, option_type, underlying, strike_parsed, close, volume, best_bid, best_ask, maturity, contracts)
        ("PETRG36", 78, "CALL", "PETR", 36.0, 8.50, 500000, 8.45, 8.55, maturity, 12000),
        ("PETRG38", 78, "CALL", "PETR", 38.0, 7.20, 1200000, 7.15, 7.25, maturity, 30000),
        ("PETRG40", 78, "CALL", "PETR", 40.0, 6.10, 2000000, 6.05, 6.15, maturity, 50000),
        ("PETRG42", 78, "CALL", "PETR", 42.0, 5.00, 800000, 4.95, 5.05, maturity, 20000),
        ("PETRS36", 82, "PUT",  "PETR", 36.0, 2.30, 300000, 2.25, 2.35, maturity, 8000),
        ("PETRS38", 82, "PUT",  "PETR", 38.0, 3.50, 900000, 3.45, 3.55, maturity, 22000),
        ("PETRS40", 82, "PUT",  "PETR", 40.0, 4.80, 1500000, 4.75, 4.85, maturity, 38000),
        ("PETRS42", 82, "PUT",  "PETR", 42.0, 6.20, 600000, 6.15, 6.25, maturity, 15000),
    ]

    for s in samples:
        conn.execute(
            """INSERT INTO cotahist_derivatives
               (refdate, bdi_code, symbol, market_type, open, high, low, close,
                best_bid, best_ask, trade_count, contracts, volume, strike,
                maturity, lot_size, underlying, option_type, strike_parsed, _ingested_at)
               VALUES (?, ?, ?, 60, ?, ?, ?, ?, ?, ?, 100, ?, ?, ?, ?, 100, ?, ?, ?, '2026-01-15')""",
            (sample_date, s[1], s[0],
             s[5], s[5], s[5], s[5],   # open, high, low, close = option price
             s[7], s[8],                # best_bid, best_ask
             s[10],                     # contracts
             s[6],                      # volume
             s[4],                      # strike (same as strike_parsed)
             s[9],                      # maturity
             s[3],                      # underlying
             s[2],                      # option_type
             s[4]),                     # strike_parsed
        )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def options_env(tmp_path: Path, monkeypatch):
    """Set up synthetic cotahist.db with derivatives data."""
    db_path = _make_derivatives_db(tmp_path)

    # Patch the db_path + connect in the derivatives catalog.
    monkeypatch.setattr(
        "data_sources.b3.cotahist_derivatives.catalog.db_path", lambda: db_path)

    def mock_connect(read_only=True):
        c = sqlite3.connect(f"file:{db_path}?mode=ro" if read_only else str(db_path),
                            uri=read_only)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(
        "data_sources.b3.cotahist_derivatives.catalog.connect", mock_connect)
    return db_path
