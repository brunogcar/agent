"""tests/data_sources/b3/test_api_query.py -- Tests for B3 API query engine.

Uses synthetic SQLite DBs (in tmp_path). Never touches real B3 data.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.b3.api.catalog import B3_TABLES, ensure_schema


@pytest.fixture
def b3_db(tmp_path, monkeypatch):
    """Create synthetic B3 instruments + trades databases."""
    b3_dir = tmp_path / "b3"
    b3_dir.mkdir(parents=True, exist_ok=True)

    # Instruments DB
    instr_path = b3_dir / "instruments.db"
    conn = sqlite3.connect(str(instr_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn, "instruments", [
        "RptDt", "TckrSymb", "ISIN", "SgmtNm", "MktNm", "CrpnNm",
        "SpcfctnCd", "CorpGovnLvlNm", "MktCptlstn",
    ])
    instruments = [
        ("2026-07-23", "PETR4", "BRPETRACNPR6", "EQUITY-CASH", "CASH",
         "PETROLEO BRASILEIRO S.A. PETROBRAS", "PN", "N2", "500000000000"),
        ("2026-07-23", "PETR3", "BRPETRACNOR6", "EQUITY-CASH", "CASH",
         "PETROLEO BRASILEIRO S.A. PETROBRAS", "ON", "N2", "300000000000"),
        ("2026-07-23", "VALE3", "BRVALEACNPA5", "EQUITY-CASH", "CASH",
         "VALE S.A.", "ON", "N2", "400000000000"),
        ("2026-07-23", "ITUB4", "BRITUBACNTR5", "EQUITY-CASH", "CASH",
         "ITAÚ UNIBANCO HOLDING S.A.", "PN", "NM", "250000000000"),
    ]
    for row in instruments:
        conn.execute(
            "INSERT INTO instruments (RptDt, TckrSymb, ISIN, SgmtNm, MktNm, CrpnNm, "
            "SpcfctnCd, CorpGovnLvlNm, MktCptlstn, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row + ("2026-07-23T12:00:00",),
        )
    conn.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
        "VALUES ('instruments', '2026-07-23', '2026-07-23T12:00:00', 4, 1)"
    )
    conn.commit()
    conn.close()

    # Trades DB
    trades_path = b3_dir / "trades.db"
    conn2 = sqlite3.connect(str(trades_path))
    conn2.row_factory = sqlite3.Row
    ensure_schema(conn2, "trades", [
        "RptDt", "TckrSymb", "ISIN", "SgmtNm",
        "MinPric", "MaxPric", "LastPric", "NtlFinVol",
    ])
    trades = [
        ("2026-07-23", "PETR4", "BRPETRACNPR6", "EQUITY-CASH", "38.50", "39.20", "38.90", "5000000"),
        ("2026-07-23", "VALE3", "BRVALEACNPA5", "EQUITY-CASH", "60.00", "61.50", "60.80", "3000000"),
    ]
    for row in trades:
        conn2.execute(
            "INSERT INTO trades (RptDt, TckrSymb, ISIN, SgmtNm, MinPric, MaxPric, LastPric, "
            "NtlFinVol, _ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row + ("2026-07-23T12:00:00",),
        )
    conn2.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
        "VALUES ('trades', '2026-07-23', '2026-07-23T12:00:00', 2, 1)"
    )
    conn2.commit()
    conn2.close()

    # Monkeypatch db_path + connect to use our temp DBs
    def mock_db_path(table_name):
        return b3_dir / B3_TABLES[table_name]["db_file"]

    def mock_connect(table_name, read_only=True):
        path = b3_dir / B3_TABLES[table_name]["db_file"]
        if read_only:
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.b3.api.catalog.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.b3.api.catalog.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.api.query_engine.connect", mock_connect)
    monkeypatch.setattr("data_sources.b3.api.query_engine.db_path", mock_db_path)
    return b3_dir


class TestB3Query:
    def test_query_by_ticker(self, b3_db):
        from data_sources.b3.api.query_engine import query
        result = query(table="instruments", ticker="PETR4")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["rows"][0]["TckrSymb"] == "PETR4"

    def test_query_all(self, b3_db):
        from data_sources.b3.api.query_engine import query
        result = query(table="instruments", limit=10)
        assert result["status"] == "ok"
        assert result["count"] == 4

    def test_query_specific_columns(self, b3_db):
        from data_sources.b3.api.query_engine import query
        result = query(table="instruments", ticker="PETR4", columns=["TckrSymb", "CrpnNm"])
        assert result["status"] == "ok"
        assert "TckrSymb" in result["columns"]
        assert "CrpnNm" in result["columns"]
        assert "ISIN" not in result["columns"]

    def test_query_trades(self, b3_db):
        from data_sources.b3.api.query_engine import query
        result = query(table="trades", ticker="PETR4")
        assert result["status"] == "ok"
        assert result["rows"][0]["LastPric"] == "38.90"

    def test_query_not_found(self, b3_db):
        from data_sources.b3.api.query_engine import query
        result = query(table="instruments", ticker="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_query_filter(self, b3_db):
        from data_sources.b3.api.query_engine import query
        result = query(table="instruments", filters={"SpcfctnCd": "PN"})
        assert result["status"] == "ok"
        assert result["count"] == 2  # PETR4 + ITUB4


class TestB3LookupTicker:
    def test_lookup(self, b3_db):
        from data_sources.b3.api.query_engine import lookup_ticker
        result = lookup_ticker(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["instrument"]["CrpnNm"] == "PETROLEO BRASILEIRO S.A. PETROBRAS"

    def test_lookup_not_found(self, b3_db):
        from data_sources.b3.api.query_engine import lookup_ticker
        result = lookup_ticker(ticker="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_lookup_no_ticker(self, b3_db):
        from data_sources.b3.api.query_engine import lookup_ticker
        result = lookup_ticker()
        assert result["status"] == "error"


class TestB3SearchCompany:
    def test_search(self, b3_db):
        from data_sources.b3.api.query_engine import search_company
        result = search_company(name="PETROBRAS")
        assert result["status"] == "ok"
        assert result["count"] >= 1

    def test_search_not_found(self, b3_db):
        from data_sources.b3.api.query_engine import search_company
        result = search_company(name="NONEXISTENT")
        assert result["status"] == "not_found"


class TestB3Status:
    def test_status(self, b3_db):
        from data_sources.b3.api.query_engine import status
        result = status()
        assert result["status"] == "ok"
        assert "instruments" in result["tables"]
        assert result["tables"]["instruments"]["rows"] == 4
        assert "trades" in result["tables"]
        assert result["tables"]["trades"]["rows"] == 2
