"""tests/data_sources/b3/api/test_api_open_positions.py -- Open positions queries.

[v1.3] Tests for the open_positions() + lookup_option_positions() functions
added to data_sources/b3/api/query_engine.py for the options skill's new
"Posições em Aberto" tab.

Uses synthetic derivatives.db + instruments.db (in tmp_path). Never touches
real B3 data.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.b3.api.catalog import B3_TABLES, ensure_schema


@pytest.fixture
def b3_open_pos_db(tmp_path, monkeypatch):
    """Create synthetic b3/derivatives.db + b3/instruments.db with open positions.

    Builds:
      - derivatives.db with 8 PETR options (4 CALL + 4 PUT) at strikes 36-42,
        plus a zero-position row (PETRG44) + a FORWARD row (PETRF38) that
        should be filtered out.
      - instruments.db with matching option metadata (ExrcPric, XprtnDt, etc.).
    """
    b3_dir = tmp_path / "b3"
    b3_dir.mkdir(parents=True, exist_ok=True)

    # ── derivatives.db ────────────────────────────────────────────────────
    deriv_path = b3_dir / B3_TABLES["derivatives"]["db_file"]
    conn = sqlite3.connect(str(deriv_path))
    conn.row_factory = sqlite3.Row
    deriv_cols = [
        "RptDt", "TckrSymb", "Asst", "ISIN", "SgmtNm",
        "OpnIntrst", "VartnOpnIntrst", "CvrdQty", "TtlBlckdPos",
        "UcvrdQty", "TtlPos", "BrrwrQty", "LndrQty", "FwdPric",
        "OptnStyle", "XprtnDt", "UndrlygTckrSymb",
    ]
    ensure_schema(conn, "derivatives", deriv_cols)

    deriv_samples = [
        # RptDt, Tckr, Asst, ISIN, Sgmt, OI, VarOI, Cvrd, Blckd, Ucvrd, Ttl, Brrwr, Lndr, Fwd, Style, Xprt, Undrlyg
        ("2026-01-15", "PETRG36", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "12.000", "500",  "4.000",  "2.000", "6.000", "12.000",
         "7.000", "5.000", "38,20", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRG38", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "30.000", "1.500", "10.000", "5.000",  "15.000", "30.000",
         "18.000", "12.000", "38,40", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRG40", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "50.000", "2.000", "20.000", "10.000", "20.000", "50.000",
         "30.000", "20.000", "38,60", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRG42", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "20.000", "-500",  "8.000",  "4.000", "8.000",  "20.000",
         "12.000", "8.000",  "38,80", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRS36", "PETR", "BRPETRACNPR6", "EQUITY PUT",
         "8.000",  "200",  "3.000",  "1.000", "4.000",  "8.000",
         "5.000", "3.000",  "38,20", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRS38", "PETR", "BRPETRACNPR6", "EQUITY PUT",
         "22.000", "800",   "8.000",  "3.000", "11.000", "22.000",
         "13.000", "9.000",  "38,40", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRS40", "PETR", "BRPETRACNPR6", "EQUITY PUT",
         "38.000", "1.200", "15.000", "5.000", "18.000", "38.000",
         "22.000", "16.000", "38,60", "AMER", "2026-08-17", "PETR4"),
        ("2026-01-15", "PETRS42", "PETR", "BRPETRACNPR6", "EQUITY PUT",
         "15.000", "-200",  "5.000",  "2.000", "8.000",  "15.000",
         "9.000", "6.000",  "38,80", "AMER", "2026-08-17", "PETR4"),
        # Zero-position row — should be filtered out.
        ("2026-01-15", "PETRG44", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "0", "0", "0", "0", "0", "0", "0", "0", "39,00", "AMER", "2026-08-17", "PETR4"),
        # FORWARD segment — should be filtered out (not EQUITY CALL/PUT).
        ("2026-01-15", "PETRF38", "PETR", "BRPETRACNPR6", "FORWARD",
         "99.999", "0", "0", "0", "0", "99.999", "0", "0", "38,40", "AMER", "2026-08-17", "PETR4"),
    ]
    for row in deriv_samples:
        conn.execute(
            "INSERT INTO derivatives (" + ", ".join(deriv_cols) + ", _ingested_at) "
            "VALUES (" + ", ".join(["?"] * (len(deriv_cols) + 1)) + ")",
            row + ("2026-01-15T12:00:00",),
        )
    conn.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
        "VALUES ('derivatives', '2026-01-15', '2026-01-15T12:00:00', 10, 1)"
    )
    conn.commit()
    conn.close()

    # ── instruments.db ────────────────────────────────────────────────────
    instr_path = b3_dir / B3_TABLES["instruments"]["db_file"]
    conn = sqlite3.connect(str(instr_path))
    conn.row_factory = sqlite3.Row
    instr_cols = [
        "RptDt", "TckrSymb", "ISIN", "SgmtNm", "CrpnNm",
        "ExrcPric", "XprtnDt", "OptnStyle", "OptnTp", "UndrlygTckrSymb1",
    ]
    ensure_schema(conn, "instruments", instr_cols)

    instr_samples = [
        ("PETRG36", "36,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRG38", "38,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRG40", "40,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRG42", "42,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS36", "36,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS38", "38,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS40", "40,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS42", "42,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETR4",   "",      "",           "",     "",     "PETROLEO BRASILEIRO S.A. PETROBRAS", ""),
    ]
    for ticker, exrc, xprt, style, optp, crpn, undr in instr_samples:
        conn.execute(
            "INSERT INTO instruments (RptDt, TckrSymb, CrpnNm, ExrcPric, XprtnDt, "
            "OptnStyle, OptnTp, UndrlygTckrSymb1, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-01-15", ticker, crpn, exrc, xprt, style, optp, undr,
             "2026-01-15T12:00:00"),
        )
    conn.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
        "VALUES ('instruments', '2026-01-15', '2026-01-15T12:00:00', 9, 1)"
    )
    conn.commit()
    conn.close()

    # ── Monkeypatch db_path + connect ─────────────────────────────────────
    def mock_db_path(table_name):
        return b3_dir / B3_TABLES[table_name]["db_file"]

    def mock_connect(table_name, read_only=True):
        path = b3_dir / B3_TABLES[table_name]["db_file"]
        if not path.exists():
            if read_only:
                raise FileNotFoundError(f"B3 {table_name} database not found at {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
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


class TestOpenPositions:
    def test_open_positions_basic(self, b3_open_pos_db):
        """open_positions() returns the 8 expected PETR options (zero + FORWARD filtered)."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "ok"
        assert result["underlying"] == "PETR"
        assert result["count"] == 8  # 10 rows - 1 zero-position - 1 FORWARD
        assert result["instruments_ok"] is True
        assert result["refdate"] == "2026-01-15"

    def test_open_positions_normalizes_ticker(self, b3_open_pos_db):
        """open_positions('PETR4') strips the trailing digit."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR4")
        assert result["status"] == "ok"
        assert result["underlying"] == "PETR"

    def test_open_positions_summary(self, b3_open_pos_db):
        """Summary aggregates CALL vs PUT totals correctly."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "ok"
        summary = result["summary"]
        # CALL OI = 12+30+50+20 = 112 thousand contracts.
        assert summary["CALL"]["oi"] == 112_000
        # PUT OI = 8+22+38+15 = 83 thousand contracts.
        assert summary["PUT"]["oi"] == 83_000
        # CALL covered = 4+10+20+8 = 42.
        assert summary["CALL"]["covered"] == 42_000
        # CALL holders (BrrwrQty) = 7+18+30+12 = 67.
        assert summary["CALL"]["holders"] == 67_000
        # CALL writers (LndrQty) = 5+12+20+8 = 45.
        assert summary["CALL"]["writers"] == 45_000

    def test_open_positions_by_strike(self, b3_open_pos_db):
        """by_strike aggregates OI per strike for the bar chart."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "ok"
        by_strike = result["by_strike"]
        # 4 strikes (36, 38, 40, 42), sorted ascending.
        assert len(by_strike) == 4
        assert by_strike[0]["strike"] == 36.0
        assert by_strike[-1]["strike"] == 42.0
        # Strike 36: CALL OI = 12000, PUT OI = 8000.
        s36 = next(s for s in by_strike if s["strike"] == 36.0)
        assert s36["call_oi"] == 12_000
        assert s36["put_oi"] == 8_000
        assert s36["call_count"] == 1
        assert s36["put_count"] == 1

    def test_open_positions_detail_join(self, b3_open_pos_db):
        """Detail rows include strike + expiration from instruments.db join."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "ok"
        detail = result["detail"]
        # Find PETRG38 — should have strike=38.0 + expiration=2026-08-17.
        g38 = next(d for d in detail if d["ticker"] == "PETRG38")
        assert g38["strike"] == 38.0
        assert g38["expiration"] == "2026-08-17"
        assert g38["optn_style"] == "AMER"
        assert g38["company"] == "PETROLEO BRASILEIRO S.A. PETROBRAS"
        # days_to_expiration should be a non-negative int (computed from today).
        assert g38["days_to_expiration"] is not None
        assert isinstance(g38["days_to_expiration"], int)

    def test_open_positions_filters_zero_position(self, b3_open_pos_db):
        """PETRG44 has all-zero positions → excluded from detail."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "ok"
        tickers = [d["ticker"] for d in result["detail"]]
        assert "PETRG44" not in tickers

    def test_open_positions_filters_forward_segment(self, b3_open_pos_db):
        """PETRF38 (FORWARD segment) → excluded from detail."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "ok"
        tickers = [d["ticker"] for d in result["detail"]]
        assert "PETRF38" not in tickers

    def test_open_positions_not_found(self, b3_open_pos_db):
        """open_positions('XXXX') → not_found (no matching tickers)."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="XXXX")
        assert result["status"] == "not_found"

    def test_open_positions_no_underlying(self, b3_open_pos_db):
        """open_positions('') → error."""
        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="")
        assert result["status"] == "error"

    def test_open_positions_not_synced(self, tmp_path, monkeypatch):
        """If derivatives.db doesn't exist → not_synced."""
        from data_sources.b3.api.catalog import B3_TABLES

        b3_dir = tmp_path / "b3"
        b3_dir.mkdir(parents=True, exist_ok=True)

        def mock_db_path(table_name):
            return b3_dir / B3_TABLES[table_name]["db_file"]

        def mock_connect(table_name, read_only=True):
            path = b3_dir / B3_TABLES[table_name]["db_file"]
            if not path.exists() and read_only:
                raise FileNotFoundError(f"B3 {table_name} database not found at {path}")
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

        from data_sources.b3.api.query_engine import open_positions
        result = open_positions(underlying="PETR")
        assert result["status"] == "not_synced"


class TestLookupOptionPositions:
    def test_lookup_basic(self, b3_open_pos_db):
        """lookup_option_positions('PETRG38') returns the row's positions."""
        from data_sources.b3.api.query_engine import lookup_option_positions
        result = lookup_option_positions(ticker="PETRG38")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETRG38"
        assert result["oi"] == 30_000
        assert result["covered"] == 10_000
        assert result["uncovered"] == 15_000
        assert result["holders"] == 18_000
        assert result["writers"] == 12_000
        assert result["forward"] == 38.40

    def test_lookup_not_found(self, b3_open_pos_db):
        """lookup_option_positions('XXXX') → not_found."""
        from data_sources.b3.api.query_engine import lookup_option_positions
        result = lookup_option_positions(ticker="XXXX")
        assert result["status"] == "not_found"

    def test_lookup_no_ticker(self, b3_open_pos_db):
        """lookup_option_positions('') → error."""
        from data_sources.b3.api.query_engine import lookup_option_positions
        result = lookup_option_positions(ticker="")
        assert result["status"] == "error"

    def test_lookup_normalizes_case(self, b3_open_pos_db):
        """lookup_option_positions('petrg38') is case-insensitive."""
        from data_sources.b3.api.query_engine import lookup_option_positions
        result = lookup_option_positions(ticker="petrg38")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETRG38"
