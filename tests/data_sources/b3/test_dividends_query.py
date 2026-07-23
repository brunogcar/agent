"""tests/data_sources/b3/test_dividends_query.py -- Tests for B3 dividends query engine.

Uses synthetic SQLite DB (in tmp_path). Never touches real data.
"""

from __future__ import annotations

import sqlite3
import pytest

from data_sources.b3.dividends.catalog import SCHEMA_SQL


@pytest.fixture
def div_db(tmp_path, monkeypatch):
    """Create a synthetic dividends database."""
    db_path = tmp_path / "dividends.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    # Insert test data
    conn.execute(
        "INSERT INTO cash_dividends (ticker, label, isin_code, approved_on, last_date_prior, rate, related_to, payment_date, _ingested_at) "
        "VALUES ('PETR4', 'Dividendo', 'BRPETRACNPR6', '2024-04-15', '2024-04-10', 1.55, '1T2024', '2024-05-15', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO cash_dividends (ticker, label, isin_code, approved_on, last_date_prior, rate, related_to, payment_date, _ingested_at) "
        "VALUES ('PETR4', 'JCP', 'BRPETRACNPR6', '2024-08-15', '2024-08-10', 0.35, '2T2024', '2024-09-15', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO stock_dividends (ticker, label, isin_code, approved_on, last_date_prior, factor, asset_issued, _ingested_at) "
        "VALUES ('PETR4', 'Bonificacao', 'BRPETRACNPR6', '2023-06-01', '2023-05-25', 0.05, 'BRPETRACNPR6', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO sync_state (ticker, synced_at, cash_count, stock_count, sub_count) "
        "VALUES ('PETR4', '2024-01-01T12:00:00', 2, 1, 0)"
    )
    conn.commit()
    conn.close()

    from pathlib import Path
    def mock_db_path():
        return db_path

    def mock_connect(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.b3.dividends.catalog.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.b3.dividends.catalog.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.dividends.query_engine.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.dividends.query_engine.db_path", mock_db_path)
    return db_path


class TestDividendsQuery:
    def test_query_dividends(self, div_db):
        from data_sources.b3.dividends.query_engine import dividends
        result = dividends(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["count"] == 2
        # Should be sorted by approved_on DESC
        assert result["dividends"][0]["approved_on"] == "2024-08-15"

    def test_query_dividends_has_values(self, div_db):
        """Verify dividend values are returned with rate + dates."""
        from data_sources.b3.dividends.query_engine import dividends
        result = dividends(ticker="PETR4")
        d = result["dividends"][0]
        assert d["rate"] == 0.35
        assert d["label"] == "JCP"
        assert d["approved_on"] == "2024-08-15"
        assert d["payment_date"] == "2024-09-15"
        assert d["related_to"] == "2T2024"

    def test_query_not_found(self, div_db):
        from data_sources.b3.dividends.query_engine import dividends
        result = dividends(ticker="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_query_no_ticker(self, div_db):
        from data_sources.b3.dividends.query_engine import dividends
        result = dividends()
        assert result["status"] == "error"

    def test_stock_dividends(self, div_db):
        from data_sources.b3.dividends.query_engine import stock_dividends
        result = stock_dividends(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_subscriptions_empty(self, div_db):
        from data_sources.b3.dividends.query_engine import subscriptions
        result = subscriptions(ticker="PETR4")
        assert result["status"] == "not_found"
        assert result["count"] == 0

    def test_status(self, div_db):
        from data_sources.b3.dividends.query_engine import status
        result = status()
        assert result["status"] == "ok"
        assert result["totals"]["cash"] == 2
        assert result["totals"]["stock"] == 1
        assert len(result["synced_tickers"]) == 1
        assert result["synced_tickers"][0]["ticker"] == "PETR4"
