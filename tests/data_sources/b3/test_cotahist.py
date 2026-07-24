"""tests/data_sources/b3/test_cotahist.py -- Tests for COTAHIST sub-domain.

Uses synthetic SQLite DB. No real downloads.
Tests the parser with real COTAHIST-format lines.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.b3.cotahist.catalog import SCHEMA_SQL


@pytest.fixture
def cotahist_db(tmp_path, monkeypatch):
    """Create a synthetic cotahist.db with test data."""
    db_path = tmp_path / "cotahist.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # Create schema (strip the DROP line for test fixture)
    schema_no_drop = SCHEMA_SQL.replace("DROP TABLE IF EXISTS cotahist;\n", "")
    conn.executescript(schema_no_drop)

    # Insert test OHLCV data for PETR4
    test_rows = [
        # (refdate, symbol, corp_name, open, high, low, close, volume, isin, market_type, _ingested_at)
        ("2025-01-02", "PETR4", "PETROBRAS", 38.50, 39.20, 38.30, 38.95, 50000000, "BRPETRACNPR6", 10, "2025-01-02T10:00:00"),
        ("2025-01-03", "PETR4", "PETROBRAS", 38.95, 40.10, 38.80, 40.00, 55000000, "BRPETRACNPR6", 10, "2025-01-02T10:00:00"),
        ("2025-06-15", "VALE3", "VALE", 60.50, 61.20, 60.30, 60.95, 40000000, "BRVALEACNOR0", 10, "2025-01-02T10:00:00"),
    ]
    for r in test_rows:
        conn.execute(
            "INSERT INTO cotahist (refdate, symbol, corp_name, open, high, low, close, "
            "volume, isin, market_type, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            r,
        )

    # Insert sync_state
    conn.execute(
        "INSERT INTO sync_state (year, synced_at, rows_added, duration_s) "
        "VALUES (2025, '2025-01-02T10:00:00', 3, 120.5)",
    )
    conn.commit()
    conn.close()

    def mock_db_path():
        return db_path

    def mock_connect(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.b3.cotahist.catalog.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.b3.cotahist.catalog.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.cotahist.query_engine.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.cotahist.query_engine.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.b3.cotahist.sync_engine.connect", mock_connect)
    return db_path


# ════════════════════════════════════════════════════════════════════════════
# PARSER TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestParser:

    def test_parse_line_vale3(self):
        """Test parsing a real COTAHIST line for VALE3 (from user's data)."""
        from data_sources.b3.cotahist.sync_engine import _parse_line
        # Real COTAHIST line (type 01, VALE3, 2025-01-27) — from user's actual data
        line = "012025012702VALE3       010VALE        ON      NM   R$  000000000528900000000053980000000005257000000000535800000000053960000000005395000000000539653601000000000024531300000000131450746100000000000000009999123100000010000000000000BRVALEACNOR0212"
        # Pad to 245 chars if needed
        line = line.ljust(245)
        row = _parse_line(line)

        assert row is not None
        assert row["regtype"] == "01"  # daily quote record
        assert row["symbol"] == "VALE3"
        assert row["refdate"] == "2025-01-27"
        assert row["open"] == 52.89    # 0000000005289 / 100
        assert row["high"] == 53.98
        assert row["low"] == 52.57
        assert row["close"] == 53.96
        assert row["isin"] == "BRVALEACNOR0"

    def test_parse_line_skip_header(self):
        """Header lines (type 00) should be skipped by caller, not _parse_line."""
        from data_sources.b3.cotahist.sync_engine import _parse_line
        # Header line starts with 00 — _parse_line still parses it
        line = "00" + " " * 243
        row = _parse_line(line)
        assert row is not None
        assert row["regtype"] == "00"

    def test_parse_line_numeric_conversion(self):
        """Verify implicit 2-decimal conversion: 5289 / 100 = 52.89"""
        from data_sources.b3.cotahist.sync_engine import _parse_line
        # Use real VALE3 line — open=52.89 confirms the /100 conversion
        line = "012025012702VALE3       010VALE        ON      NM   R$  000000000528900000000053980000000005257000000000535800000000053960000000005395000000000539653601000000000024531300000000131450746100000000000000009999123100000010000000000000BRVALEACNOR0212"
        line = line.ljust(245)
        row = _parse_line(line)
        assert row is not None
        # open = int("0000000005289") / 100 = 52.89
        assert row["open"] == 52.89
        # volume = int("00000000013145074610") / 100 — wait, volume is 18 chars
        # Actually volume positions 171-188 = 18 chars
        # The user's line: "536010000000000024531300000000131450746100000000000000009999"
        # Let me just verify open/high/low/close are correct (they're 13 chars each)
        assert row["high"] == 53.98
        assert row["low"] == 52.57
        assert row["close"] == 53.96


# ════════════════════════════════════════════════════════════════════════════
# QUERY TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestQuery:

    def test_query_by_ticker(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import query
        r = query(ticker="PETR4")
        assert r["status"] == "ok"
        assert r["count"] == 2

    def test_query_by_year(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import query
        r = query(year=2025)
        assert r["status"] == "ok"
        assert r["count"] == 3

    def test_query_date_range(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import query
        r = query(ticker="PETR4", date_from="2025-01-01", date_to="2025-01-31")
        assert r["status"] == "ok"
        assert r["count"] == 2

    def test_query_not_found(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import query
        r = query(ticker="ZZZZ4")
        assert r["status"] == "not_found"

    def test_query_limit(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import query
        r = query(year=2025, limit=1)
        assert r["status"] == "ok"
        assert r["count"] == 1


class TestStatus:

    def test_status_ok(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import status
        r = status()
        assert r["status"] == "ok"
        assert r["total_rows"] == 3
        assert r["distinct_tickers"] == 2
        assert len(r["years_synced"]) == 1
        assert r["years_synced"][0]["year"] == 2025


class TestRoute:

    def test_route_no_mode(self):
        from data_sources.b3.cotahist import route
        r = route()
        assert r["status"] == "error"
        assert "mode required" in r["error"]

    def test_route_unknown_mode(self):
        from data_sources.b3.cotahist import route
        r = route(mode="invalid")
        assert r["status"] == "error"

    def test_route_dispatches_to_status(self, cotahist_db):
        from data_sources.b3.cotahist import route
        r = route(mode="status")
        assert r["status"] == "ok"
