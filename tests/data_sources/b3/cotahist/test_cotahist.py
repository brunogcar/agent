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
        from data_sources.b3.cotahist.status_reporter import status
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


# ════════════════════════════════════════════════════════════════════════════
# [v1.28.2] THE SHARE-LIKE UNIVERSE + THE BDR BACKFILL PROBE
# The quote queries scoped bdi_code=2 (equities): ETFs (BDI 14) never
# reached the Painel's BOVA11/SMAL11/IVVB11 KPI row, and BDR rows (BDI
# 34/35/36, once the sync filter carries them) would have met the same
# fate. market_snapshot/quotes_for now span the share-like set and each
# row exposes its bdi_code (the callers slice); _bdr_rows_missing drives
# the one-time current-year rebuild in _sync_year.
# ════════════════════════════════════════════════════════════════════════════

class TestShareLikeUniverse:

    def test_market_snapshot_spans_the_share_like_bdIs(self, cotahist_db):
        """ETF (14), FII (12) and BDR (34) rows are quoted, each carrying
        its bdi_code — the equities-only scope is gone."""
        import sqlite3 as s3
        conn = s3.connect(str(cotahist_db))
        # two sessions so variation_pct (close vs prev) exists
        for d, bova, aapl, hgbs in (("2025-07-01", 120.0, 20.0, 9.0),
                                    ("2025-07-02", 122.4, 21.2, 9.2)):
            for sym, name, bdi, close in (("BOVA11", "ISHARES BOVA", 14, bova),
                                          ("AAPL34", "APPLE BDR", 34, aapl),
                                          ("HGBS11", "CSHG FII", 12, hgbs)):
                conn.execute(
                    "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
                    " market_type, close, volume, trade_count, _ingested_at)"
                    " VALUES (?, ?, ?, ?, 10, ?, 1000, 500, 'x')",
                    (d, sym, name, bdi, close))
        conn.commit()
        conn.close()

        from data_sources.b3.cotahist.query_engine import market_snapshot
        snap = market_snapshot()
        assert snap["status"] == "ok"
        by_tk = {s["ticker"]: s for s in snap["symbols"]}
        assert by_tk["BOVA11"]["bdi_code"] == 14
        assert by_tk["AAPL34"]["bdi_code"] == 34
        assert by_tk["HGBS11"]["bdi_code"] == 12
        # close + signed variation vs the previous session
        assert by_tk["BOVA11"]["close"] == 122.4
        assert round(by_tk["BOVA11"]["variation_pct"], 2) == 2.0
        assert round(by_tk["AAPL34"]["variation_pct"], 2) == 6.0

    def test_market_snapshot_still_excludes_non_share_like_rows(self, cotahist_db):
        """Fractional (96) duplicates stay out; NULL-bdi rows stay out —
        only the share-like BDI set is quoted."""
        import sqlite3 as s3
        conn = s3.connect(str(cotahist_db))
        # proper equity rows for two sessions…
        for d, close in (("2025-06-15", 60.95), ("2025-06-16", 61.20)):
            conn.execute(
                "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
                " market_type, close, volume, trade_count, _ingested_at)"
                " VALUES (?, 'PETR4', 'PETROBRAS', 2, 10, ?, 5.0e7, 88000, 'x')",
                (d, close))
        # …plus a fractional duplicate of the second session (bdi 96,
        # fracionário market) with a wilder close — it must not leak in
        conn.execute(
            "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
            " market_type, close, volume, trade_count, _ingested_at)"
            " VALUES ('2025-06-16', 'PETR4', 'PETROBRAS', 96, 70, 99.0,"
            " 100, 10, 'x')")
        conn.commit()
        conn.close()

        from data_sources.b3.cotahist.query_engine import market_snapshot
        snap = market_snapshot()
        assert snap["status"] == "ok"
        petr = [s for s in snap["symbols"] if s["ticker"] == "PETR4"]
        assert len(petr) == 1                     # one row, not the duplicate
        assert petr[0]["close"] == 61.20          # the bdi 2 (lote padrão) close
        assert round(petr[0]["variation_pct"], 2) == 0.41
        # the fixture's NULL-bdi VALE3 row never shows up
        assert "VALE3" not in {s["ticker"] for s in snap["symbols"]}

    def test_quotes_for_covers_non_equity_positions(self, cotahist_db):
        """A portfolio can hold ETFs/FIIs/BDRs — quotes_for quotes them
        (the old bdi=2 scope left those positions quote-less)."""
        import sqlite3 as s3
        conn = s3.connect(str(cotahist_db))
        for d, close in (("2025-07-01", 300.0), ("2025-07-02", 306.0)):
            conn.execute(
                "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
                " market_type, close, volume, trade_count, _ingested_at)"
                " VALUES (?, 'IVVB11', 'ISHARES S&P 500', 14, 10, ?, 1000,"
                " 200, 'x')", (d, close))
        conn.commit()
        conn.close()

        from data_sources.b3.cotahist.query_engine import quotes_for
        r = quotes_for(["IVVB11", "NOPE4"])
        assert r["status"] == "ok"
        got = {s["ticker"]: s for s in r["symbols"]}
        assert got["IVVB11"]["close"] == 306.0
        assert round(got["IVVB11"]["variation_pct"], 2) == 2.0
        assert got["IVVB11"]["bdi_code"] == 14
        assert "NOPE4" not in got      # absent symbols degrade per-ticker


class TestBdrBackfillProbe:

    def _conn(self, db):
        import sqlite3 as s3
        c = s3.connect(str(db))
        c.row_factory = s3.Row
        return c

    def test_missing_when_the_year_has_no_bdr_rows(self, cotahist_db):
        """A pre-extension DB (equities only) reports the year BDR-less —
        the signal that makes _sync_year rebuild the current year once."""
        from data_sources.b3.cotahist.sync_engine import _bdr_rows_missing
        conn = self._conn(cotahist_db)
        try:
            assert _bdr_rows_missing(conn, 2025) is True
        finally:
            conn.close()

    def test_present_once_a_bdr_row_exists(self, cotahist_db):
        """A single BDR row anywhere in the year satisfies the probe (the
        incremental path resumes; no rebuild loop)."""
        import sqlite3 as s3
        conn = s3.connect(str(cotahist_db))
        conn.execute(
            "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
            " market_type, close, volume, trade_count, _ingested_at)"
            " VALUES ('2025-06-16', 'AAPL34', 'APPLE BDR', 34, 10, 21.0,"
            " 1000, 400, 'x')")
        conn.commit()
        conn.close()

        from data_sources.b3.cotahist.sync_engine import _bdr_rows_missing
        conn = self._conn(cotahist_db)
        try:
            assert _bdr_rows_missing(conn, 2025) is False
        finally:
            conn.close()

    def test_probe_is_year_scoped(self, cotahist_db):
        """BDR rows in OTHER years don't satisfy the probe for 2026."""
        import sqlite3 as s3
        conn = s3.connect(str(cotahist_db))
        conn.execute(
            "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
            " market_type, close, volume, trade_count, _ingested_at)"
            " VALUES ('2024-06-16', 'AAPL34', 'APPLE BDR', 34, 10, 21.0,"
            " 1000, 400, 'x')")
        conn.commit()
        conn.close()

        from data_sources.b3.cotahist.sync_engine import _bdr_rows_missing
        conn = self._conn(cotahist_db)
        try:
            assert _bdr_rows_missing(conn, 2026) is True
        finally:
            conn.close()


class TestRange52w:
    """[v1.28.3] range_52w() — the trailing-52-week high/low per symbol
    (the Painel's Tickers Observados "Máx/Mín 52 sem" columns)."""

    def _seed(self, db, rows):
        """rows: (refdate, symbol, bdi, high, low, close[, market_type])"""
        import sqlite3 as s3
        conn = s3.connect(str(db))
        for r in rows:
            mt = r[6] if len(r) > 6 else 10
            conn.execute(
                "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
                " market_type, high, low, close, volume, trade_count,"
                " _ingested_at) VALUES (?, ?, 'X', ?, ?, ?, ?, ?, 1000, 100,"
                " 'x')", (r[0], r[1], r[2], mt, r[3], r[4], r[5]))
        conn.commit()
        conn.close()

    def test_high_low_over_the_trailing_window(self, cotahist_db):
        """MAX(high)/MIN(low) over the DB's last 365 days — the anchor is
        the DB's own latest refdate, not the wall clock."""
        self._seed(cotahist_db, [
            ("2026-11-20", "PETR4", 2, 40.10, 38.00, 39.00),   # in-window high
            ("2026-10-15", "PETR4", 2, 36.00, 30.15, 31.00),   # in-window low
            ("2025-11-19", "PETR4", 2, 99.00, 25.00, 98.00),   # 1d before cutoff — OUT
            ("2025-06-10", "PETR4", 2, 41.00, 39.00, 40.50),   # ~17 months old — OUT
        ])
        from data_sources.b3.cotahist.query_engine import range_52w
        res = range_52w(["PETR4"])
        assert res["status"] == "ok"
        assert res["ref_date"] == "2026-11-20"
        assert res["window_from"] == "2025-11-20"
        row = res["symbols"][0]
        assert row["ticker"] == "PETR4"
        assert row["high_52"] == 40.10          # the 99.00 print is outside
        assert row["low_52"] == 30.15           # the 25.00 print is outside

    def test_universe_and_zero_print_guards(self, cotahist_db):
        """Fractional duplicates stay out; a spurious zero LOW never owns
        the MIN; unrequested/absent symbols are simply missing."""
        self._seed(cotahist_db, [
            ("2026-11-20", "VALE3", 2, 70.00, 65.00, 68.00),
            # zero-low print same session — the WHOLE row is dropped
            # (a corrupt print's high must not own the MAX either)
            ("2026-11-20", "VALE3", 2, 71.00, 0.0, 68.50),
            # fractional duplicate (bdi 96, mercado 70) with wilder prices
            ("2026-11-20", "VALE3", 96, 95.00, 50.00, 90.00, 70),
            # an ETF — share-like, so it IS quoted
            ("2026-11-20", "BOVA11", 14, 130.00, 125.00, 129.00),
        ])
        from data_sources.b3.cotahist.query_engine import range_52w
        res = range_52w(["VALE3", "BOVA11", "ZZZZ99"])
        assert res["status"] == "ok"
        by_tk = {s["ticker"]: s for s in res["symbols"]}
        assert by_tk["VALE3"]["high_52"] == 70.00   # the 71.00 row is gone
        assert by_tk["VALE3"]["low_52"] == 65.00     # not the 0.0, not the 50
        assert by_tk["BOVA11"]["high_52"] == 130.00  # ETF in the universe
        assert "ZZZZ99" not in by_tk                 # never-traded: absent

    def test_empty_request_short_circuits(self, cotahist_db):
        from data_sources.b3.cotahist.query_engine import range_52w
        res = range_52w([])
        assert res == {"status": "ok", "symbols": [],
                       "window_from": "", "ref_date": ""}
        # garbage shapes are dropped by the _SYMBOL_RE guard → same shape
        assert range_52w(["not a ticker!"])["status"] == "ok"
