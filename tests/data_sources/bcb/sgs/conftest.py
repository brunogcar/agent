"""tests/data_sources/bcb/sgs/conftest.py - Shared sgs_db fixture.

Creates a REAL temp SQLite DB with test data (not a mock) and monkeypatches
catalog.bcb_data_dir so all query_engine reads go to the temp DB.

Per CRITICAL RULE 9: "conftest.py must create a real temp SQLite DB with
test data (not mock)". This fixture inserts real observations for 3 series
(Selic 11, IPCA 433, USD/BRL 1) into a tmp_path sgs.db so the query_engine
tests exercise real SQL against a real DB.
"""
from __future__ import annotations

import sqlite3
import pytest

from data_sources.bcb.sgs import catalog


@pytest.fixture
def sgs_db(tmp_path, monkeypatch):
    """Create a temp sgs.db with test data + monkeypatch catalog.bcb_data_dir."""
    # Point catalog.bcb_data_dir at the temp dir so db_path() returns the
    # temp sgs.db.
    monkeypatch.setattr(catalog, "bcb_data_dir", lambda: tmp_path)

    db = tmp_path / "sgs.db"
    conn = sqlite3.connect(str(db))
    catalog.ensure_schema(conn)

    # Real test observations (not mocks): 3 series covering Juros/Inflacao/Cambio.
    test_data = [
        # Selic diaria (11) - 3 daily observations
        (11, "2024-01-02", 0.001234, "2024-01-05T00:00:00+00:00"),
        (11, "2024-01-03", 0.001235, "2024-01-05T00:00:00+00:00"),
        (11, "2024-01-04", 0.001236, "2024-01-05T00:00:00+00:00"),
        # IPCA mensal (433) - 2 monthly observations
        (433, "2024-01-10", 0.42, "2024-01-15T00:00:00+00:00"),
        (433, "2024-02-10", 0.38, "2024-01-15T00:00:00+00:00"),
        # USD/BRL ptax (1) - 3 daily observations
        (1, "2024-01-02", 4.9460, "2024-01-05T00:00:00+00:00"),
        (1, "2024-01-03", 4.9470, "2024-01-05T00:00:00+00:00"),
        (1, "2024-01-04", 4.9480, "2024-01-05T00:00:00+00:00"),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO series_observations "
        "(series_code, ref_date, value, synced_at) VALUES (?, ?, ?, ?)",
        test_data,
    )
    # Record sync_state for series 11 so status_reporter has data to read.
    conn.executemany(
        "INSERT OR REPLACE INTO sync_state "
        "(series_code, last_date, synced_at, row_count) VALUES (?, ?, ?, ?)",
        [
            ("11", "2024-01-04", "2024-01-05T00:00:00+00:00", 3),
            ("433", "2024-02-10", "2024-01-15T00:00:00+00:00", 2),
            ("1", "2024-01-04", "2024-01-05T00:00:00+00:00", 3),
        ],
    )
    conn.commit()
    conn.close()
    return db
