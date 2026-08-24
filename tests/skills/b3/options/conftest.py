"""Shared fixtures for the b3.options skill tests.

Builds a synthetic cotahist.db with BOTH the cotahist (equities) AND
cotahist_derivatives (options) tables populated with sample PETR data.
Also builds a synthetic sgs.db with the Selic rate (series 432) for the IV
tab's Black-Scholes engine.

[v1.2] Added sgs.db + equities PETR4 row so the IV tab can fetch:
  - spot price = 38.20 (PETR4 latest close in cotahist equities table)
  - Selic rate = 14.25 (BCB SGS series 432 = "Meta Selic Copom" % a.a.)

[v1.3] Added synthetic b3/derivatives.db + b3/instruments.db so the new
Posições em Aberto tab + the Cadeia de Opções OI/Coberta/Descoberta
enrichment can be tested. The derivatives.db uses the same option tickers
as the cotahist chain (PETRG36, PETRS36, ...) so the chain enrichment join
finds them.
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
    """Create a synthetic cotahist.db with cotahist_derivatives + cotahist tables."""
    from data_sources.b3.cotahist.catalog import (
        DERIVATIVES_SCHEMA_SQL, SCHEMA_SQL as _EQ_SCHEMA_SQL,
    )

    db_path = tmp_path / "cotahist.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Equities table (cotahist) -- used by _fetch_spot_price() to get PETR4 close.
    # Drop the DROP statement (the schema does DROP TABLE IF EXISTS cotahist;)
    # so we don't blow away the derivatives table we're about to create.
    eq_schema = _EQ_SCHEMA_SQL.replace("DROP TABLE IF EXISTS cotahist;\n", "")
    conn.executescript(eq_schema)

    # Derivatives table (cotahist_derivatives) -- options chain data.
    conn.executescript(DERIVATIVES_SCHEMA_SQL)

    # ── Equities: 1 PETR4 row with close = 38.20 ──────────────────────────
    sample_date = "2026-01-15"
    conn.execute(
        """INSERT INTO cotahist
           (refdate, symbol, bdi_code, market_type, corp_name, open, high, low,
            close, average, volume, trade_count, contracts, best_bid, best_ask,
            isin, _ingested_at)
           VALUES (?, 'PETR4', 2, 10, 'PETROBRAS PN', 38.00, 38.50, 37.90,
                   38.20, 38.20, 50000000, 12000, 1300000, 38.18, 38.22,
                   'BRPETRACNPR9', '2026-01-15')""",
        (sample_date,),
    )

    # ── Derivatives: 8 PETR options (4 calls + 4 puts) for one maturity ────
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


def _make_sgs_db(tmp_path: Path) -> Path:
    """Create a synthetic sgs.db with series 432 = 14.25 (% a.a. Meta Selic Copom)."""
    from data_sources.bcb.sgs.catalog import SCHEMA_SQL as _SGS_SCHEMA_SQL

    db_path = tmp_path / "sgs.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SGS_SCHEMA_SQL)

    # Insert one observation for series 432 = "Meta Selic Copom" (% a.a.).
    conn.execute(
        "INSERT OR REPLACE INTO series_observations "
        "(series_code, ref_date, value, synced_at) VALUES (?, ?, ?, ?)",
        (432, "2026-01-15", 14.25, "2026-01-15T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(series_code, last_date, synced_at, row_count) VALUES (?, ?, ?, ?)",
        ("432", "2026-01-15", "2026-01-15T00:00:00+00:00", 1),
    )
    conn.commit()
    conn.close()
    return db_path


def _make_b3_api_dbs(tmp_path: Path) -> Path:
    """Create synthetic b3/derivatives.db + b3/instruments.db (B3 API CSV).

    [v1.3] Used by the Posições em Aberto tab + the Cadeia de Opções OI /
    Coberta / Descoberta enrichment. The derivatives.db uses the SAME
    option tickers as the cotahist chain (PETRG36, PETRS36, ...) so the
    chain enrichment join finds them.

    Returns the b3 data directory (containing derivatives.db + instruments.db).
    """
    from data_sources.b3.api.catalog import B3_TABLES, ensure_schema

    b3_dir = tmp_path / "b3"
    b3_dir.mkdir(parents=True, exist_ok=True)

    # ── derivatives.db (17 cols; B3 API DerivativesOpenPosition) ────────
    deriv_path = b3_dir / B3_TABLES["derivatives"]["db_file"]
    conn = sqlite3.connect(str(deriv_path))
    conn.row_factory = sqlite3.Row
    # The 17 columns of the DerivativesOpenPosition table (PT-BR numerics
    # stored as TEXT — same as the real CSV bulk download).
    deriv_cols = [
        "RptDt", "TckrSymb", "Asst", "ISIN", "SgmtNm",
        "OpnIntrst", "VartnOpnIntrst", "CvrdQty", "TtlBlckdPos",
        "UcvrdQty", "TtlPos", "BrrwrQty", "LndrQty", "FwdPric",
        "OptnStyle", "XprtnDt", "UndrlygTckrSymb",
    ]
    ensure_schema(conn, "derivatives", deriv_cols)

    # 8 PETR options matching the cotahist chain tickers + 1 zero-position
    # row (PETRG44) to verify the zero-position filter.
    # Cols: RptDt, TckrSymb, Asst, ISIN, SgmtNm, OpnIntrst, VartnOpnIntrst,
    #       CvrdQty, TtlBlckdPos, UcvrdQty, TtlPos, BrrwrQty, LndrQty,
    #       FwdPric, OptnStyle, XprtnDt, UndrlygTckrSymb
    deriv_samples = [
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
        # Zero-position row — should be filtered out by open_positions().
        ("2026-01-15", "PETRG44", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "0",      "0",    "0",      "0",    "0",      "0",
         "0",    "0",      "39,00", "AMER", "2026-08-17", "PETR4"),
        # FORWARD segment row — should be filtered out (not EQUITY CALL/PUT).
        ("2026-01-15", "PETRF38", "PETR", "BRPETRACNPR6", "FORWARD",
         "99.999", "0",    "0",      "0",    "0",      "99.999",
         "0",    "0",      "38,40", "AMER", "2026-08-17", "PETR4"),
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

    # ── instruments.db (52 cols; B3 API InstrumentsConsolidated) ────────
    # We only populate the option-relevant columns: TckrSymb, ExrcPric,
    # XprtnDt, OptnStyle, OptnTp, CrpnNm, UndrlygTckrSymb1.
    instr_path = b3_dir / B3_TABLES["instruments"]["db_file"]
    conn = sqlite3.connect(str(instr_path))
    conn.row_factory = sqlite3.Row
    instr_cols = [
        "RptDt", "TckrSymb", "ISIN", "SgmtNm", "MktNm", "CrpnNm",
        "SpcfctnCd", "CorpGovnLvlNm", "MktCptlstn",
        # Option-specific columns:
        "OpnIntrst", "ExrcPric", "XprtnDt", "OptnStyle", "OptnTp",
        "UndrlygTckrSymb1", "Asst",
    ]
    ensure_schema(conn, "instruments", instr_cols)

    # Map each option ticker to its strike + expiration. The strike is the
    # same as in cotahist_derivatives (36, 38, 40, 42) so the join produces
    # consistent data. ExrcPric is in PT-BR format ("36,00").
    instr_samples = [
        # (TckrSymb, ExrcPric, XprtnDt, OptnStyle, OptnTp, CrpnNm, Undrlyg)
        ("PETRG36", "36,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRG38", "38,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRG40", "40,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRG42", "42,00", "2026-08-17", "AMER", "Call", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS36", "36,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS38", "38,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS40", "40,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        ("PETRS42", "42,00", "2026-08-17", "AMER", "Put",  "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETR4"),
        # The underlying stock ticker — present in instruments but filtered
        # out by the SgmtNm='EQUITY CALL/PUT' check in open_positions().
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

    return b3_dir


@pytest.fixture
def options_env(tmp_path: Path, monkeypatch):
    """Set up synthetic cotahist.db + sgs.db + b3/derivatives.db + b3/instruments.db for the options dashboard tests."""
    db_path = _make_derivatives_db(tmp_path)
    sgs_path = _make_sgs_db(tmp_path)
    b3_dir = _make_b3_api_dbs(tmp_path)

    # ── Patch the cotahist catalog: db_path + connect ─────────────────────
    monkeypatch.setattr(
        "data_sources.b3.cotahist.catalog.db_path", lambda: db_path)

    def mock_connect(read_only=True):
        c = sqlite3.connect(f"file:{db_path}?mode=ro" if read_only else str(db_path),
                            uri=read_only)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(
        "data_sources.b3.cotahist.catalog.connect", mock_connect)

    # ── Patch the sgs catalog: db_path + connect ──────────────────────────
    monkeypatch.setattr(
        "data_sources.bcb.sgs.catalog.db_path", lambda: sgs_path)

    def mock_sgs_connect(read_only=True):
        c = sqlite3.connect(f"file:{sgs_path}?mode=ro" if read_only else str(sgs_path),
                            uri=read_only)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(
        "data_sources.bcb.sgs.catalog.connect", mock_sgs_connect)

    # ── Patch the b3.api catalog: db_path + connect (v1.3) ───────────────
    # Used by open_positions() + lookup_option_positions() in query_engine.py.
    from data_sources.b3.api.catalog import B3_TABLES

    def mock_b3_db_path(table_name):
        return b3_dir / B3_TABLES[table_name]["db_file"]

    def mock_b3_connect(table_name, read_only=True):
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

    monkeypatch.setattr("data_sources.b3.api.catalog.db_path", mock_b3_db_path)
    monkeypatch.setattr("data_sources.b3.api.catalog.connect", mock_b3_connect)
    monkeypatch.setattr("data_sources.b3.api.query_engine.connect", mock_b3_connect)
    monkeypatch.setattr("data_sources.b3.api.query_engine.db_path", mock_b3_db_path)
    return db_path
