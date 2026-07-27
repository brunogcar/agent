"""tests/data_sources/b3/test_brapi.py -- Tests for brapi.dev sub-domain.

Mocks HTTP fetcher — no real network calls.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from data_sources.b3.brapi.catalog import SCHEMA_SQL


@pytest.fixture
def brapi_db(tmp_path, monkeypatch):
    """Create a synthetic brapi.db."""
    db_path = tmp_path / "brapi.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    # Insert test tickers
    for t in ["PETR4", "VALE3", "ITUB4", "MGLU3"]:
        conn.execute("INSERT INTO tickers (symbol, synced_at) VALUES (?, '2026-07-24')", (t,))
    # Insert test OHLCV
    conn.execute(
        "INSERT INTO quotes (symbol, date, open, high, low, close, adjusted_close, volume, synced_at) "
        "VALUES ('PETR4', '2026-07-24', 42.37, 42.91, 42.15, 42.21, 42.21, 29107700, '2026-07-24')"
    )
    conn.execute(
        "INSERT INTO quotes (symbol, date, open, high, low, close, adjusted_close, volume, synced_at) "
        "VALUES ('PETR4', '2026-07-23', 43.40, 43.49, 42.86, 42.95, 42.95, 25257900, '2026-07-24')"
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

    monkeypatch.setattr("data_sources.b3.brapi.catalog.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.b3.brapi.catalog.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.brapi.query_engine.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.brapi.query_engine.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.b3.brapi.sync_engine.connect", mock_connect)
    return db_path


class TestQuoteMode:

    @patch("data_sources.b3.brapi.query_engine.fetch_quote")
    def test_quote_from_local(self, mock_fetch, brapi_db):
        """Quote should try local DB first."""
        from data_sources.b3.brapi.query_engine import quote
        r = quote(ticker="PETR4")
        assert r["status"] == "ok"
        assert r["source"] == "local"
        assert r["price"] == 42.21
        mock_fetch.assert_not_called()

    @patch("data_sources.b3.brapi.query_engine.fetch_quote")
    def test_quote_live(self, mock_fetch, brapi_db):
        """Quote with force=True should fetch live."""
        mock_fetch.return_value = {
            "status": "ok",
            "quote": {"regularMarketPrice": 42.50, "marketCap": 600000000000,
                      "priceEarnings": 5.0, "currency": "BRL"},
        }
        from data_sources.b3.brapi.query_engine import quote
        r = quote(ticker="PETR4", force=True)
        assert r["status"] == "ok"
        assert r["source"] == "brapi_live"
        assert r["price"] == 42.50
        assert r["market_cap"] == 600000000000

    def test_quote_no_ticker(self, brapi_db):
        from data_sources.b3.brapi.query_engine import quote
        r = quote()
        assert r["status"] == "error"


class TestHistoryMode:

    def test_history_ok(self, brapi_db):
        from data_sources.b3.brapi.query_engine import history
        r = history(ticker="PETR4", days=5)
        assert r["status"] == "ok"
        assert r["count"] == 2

    def test_history_not_found(self, brapi_db):
        from data_sources.b3.brapi.query_engine import history
        r = history(ticker="ZZZZ4")
        assert r["status"] == "not_found"

    def test_history_no_ticker(self, brapi_db):
        from data_sources.b3.brapi.query_engine import history
        r = history()
        assert r["status"] == "error"


class TestTickersMode:

    def test_tickers_ok(self, brapi_db):
        from data_sources.b3.brapi.query_engine import tickers
        r = tickers()
        assert r["status"] == "ok"
        assert r["count"] == 4
        assert "PETR4" in r["tickers"]


class TestStatusMode:

    def test_status_ok(self, brapi_db):
        from data_sources.b3.brapi.status_reporter import status
        r = status()
        assert r["status"] == "ok"
        assert r["tickers"] == 4
        assert r["ohlcv_rows"] == 2


class TestRoute:

    def test_route_no_mode(self):
        from data_sources.b3.brapi import route
        r = route()
        assert r["status"] == "error"
        assert "mode required" in r["error"]

    def test_route_unknown_mode(self):
        from data_sources.b3.brapi import route
        r = route(mode="invalid")
        assert r["status"] == "error"

    def test_route_dispatches_to_status(self, brapi_db):
        from data_sources.b3.brapi import route
        r = route(mode="status")
        assert r["status"] == "ok"
