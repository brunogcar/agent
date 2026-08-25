"""tests/data_sources/b3/api/test_api_forward_positions.py -- Forward positions.

[v2.2] Tests for the forward_positions() function added to
data_sources/b3/api/query_engine.py for the term skill's stock-term
fallback. When COTAHIST has no term data (which is always for stocks —
B3 routes stock term to BTC), the term dashboard queries derivatives.db
for the EQUITY FORWARD contract snapshot (ticker = {TICKER}T).

Uses synthetic derivatives.db + instruments.db (in tmp_path). Never
touches real B3 data.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.b3.api.catalog import B3_TABLES, ensure_schema


@pytest.fixture
def b3_forward_db(tmp_path, monkeypatch):
    """Create synthetic b3/derivatives.db + b3/instruments.db with forward positions.

    Builds:
      - derivatives.db with 3 EQUITY FORWARD rows (PETR4T, VALE3T, ITUB4T)
        with realistic PT-BR formatted numbers (OpnIntrst, CurQty, FwdPric).
        Plus an EQUITY CALL option row (PETRA201) to verify it's filtered
        out, plus a bare-SgmtNm 'FORWARD' row (BBAS3T) to verify both
        segment-name variants are accepted. Plus a zero-quantity forward
        (BBSE3T) to verify forward_price_per_share=None.
      - instruments.db with matching forward-ticker metadata (CrpnNm, ISIN,
        SctyCtgyNm, SpcfctnCd).
    """
    b3_dir = tmp_path / "b3"
    b3_dir.mkdir(parents=True, exist_ok=True)

    # ── derivatives.db ────────────────────────────────────────────────────
    deriv_path = b3_dir / B3_TABLES["derivatives"]["db_file"]
    conn = sqlite3.connect(str(deriv_path))
    conn.row_factory = sqlite3.Row
    deriv_cols = [
        "RptDt", "TckrSymb", "Asst", "ISIN", "SgmtNm",
        "OpnIntrst", "CurQty", "FwdPric",
    ]
    ensure_schema(conn, "derivatives", deriv_cols)

    deriv_samples = [
        # RptDt, Tckr, Asst, ISIN, Sgmt, OI, CurQty, FwdPric
        # PETR4T — the canonical example from the task description.
        ("2026-08-21", "PETR4T", "PETR", "BRPETRTNP008", "EQUITY FORWARD",
         "1.196", "1.358.721", "58828062,67"),
        # VALE3T — another forward.
        ("2026-08-21", "VALE3T", "VALE", "BRVALEACNPA9", "EQUITY FORWARD",
         "845", "920.000", "55.200.000,00"),
        # ITUB4T — bare SgmtNm 'FORWARD' (some B3 snapshots use this).
        ("2026-08-21", "ITUB4T", "ITUB", "BRITUBACNTR6", "FORWARD",
         "312", "450.000", "13.500.000,00"),
        # BBSE3T — zero CurQty → forward_price_per_share should be None.
        ("2026-08-21", "BBSE3T", "BBSE", "BRBBSEACNPR0", "EQUITY FORWARD",
         "0", "0", "0,00"),
        # PETRA201 — an EQUITY CALL option (should NOT match forward_positions).
        ("2026-08-21", "PETRA201", "PETR", "BRPETRACNPR6", "EQUITY CALL",
         "5.000", "0", "0,00"),
    ]
    for row in deriv_samples:
        conn.execute(
            "INSERT INTO derivatives (" + ", ".join(deriv_cols) + ", _ingested_at) "
            "VALUES (" + ", ".join(["?"] * (len(deriv_cols) + 1)) + ")",
            row + ("2026-08-21T12:00:00",),
        )
    conn.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
        "VALUES ('derivatives', '2026-08-21', '2026-08-21T12:00:00', 5, 1)"
    )
    conn.commit()
    conn.close()

    # ── instruments.db ────────────────────────────────────────────────────
    instr_path = b3_dir / B3_TABLES["instruments"]["db_file"]
    conn = sqlite3.connect(str(instr_path))
    conn.row_factory = sqlite3.Row
    instr_cols = [
        "RptDt", "TckrSymb", "ISIN", "SgmtNm", "CrpnNm",
        "SctyCtgyNm", "SpcfctnCd", "ExrcPric", "XprtnDt",
        "OptnStyle", "OptnTp", "UndrlygTckrSymb1",
    ]
    ensure_schema(conn, "instruments", instr_cols)

    instr_samples = [
        # (Tckr, ISIN, CrpnNm, SctyCtgyNm, SpcfctnCd)
        ("PETR4T", "BRPETRTNP008", "PETROLEO BRASILEIRO S.A. PETROBRAS",
         "COMMON EQUITIES FORWARD", "PN      N2"),
        ("VALE3T", "BRVALEACNPA9", "VALE S.A.",
         "COMMON EQUITIES FORWARD", "ON      NM"),
        ("ITUB4T", "BRITUBACNTR6", "ITAÚ UNIBANCO HOLDING S.A.",
         "PREFERRED EQUITIES FORWARD", "PN      NM"),
        ("BBSE3T", "BRBBSEACNPR0", "BB SEGURIDADE PARTICIPACOES S.A.",
         "COMMON EQUITIES FORWARD", "ON      NM"),
    ]
    for ticker, isin, crpn, scty, spec in instr_samples:
        conn.execute(
            "INSERT INTO instruments (RptDt, TckrSymb, ISIN, CrpnNm, "
            "SctyCtgyNm, SpcfctnCd, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-08-21", ticker, isin, crpn, scty, spec,
             "2026-08-21T12:00:00"),
        )
    conn.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
        "VALUES ('instruments', '2026-08-21', '2026-08-21T12:00:00', 4, 1)"
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


class TestForwardPositions:
    def test_forward_positions_basic(self, b3_forward_db):
        """forward_positions('PETR4') returns the full snapshot for PETR4T."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4T"
        assert result["underlying"] == "PETR4"
        assert result["refdate"] == "2026-08-21"
        assert result["instruments_ok"] is True

    def test_forward_positions_constructs_ticker(self, b3_forward_db):
        """forward_positions('PETR4') constructs the forward ticker PETR4T."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4T"
        assert result["underlying"] == "PETR4"

    def test_forward_positions_passes_through_existing_t_ticker(self, b3_forward_db):
        """forward_positions('PETR4T') uses the ticker as-is."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4T")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4T"
        assert result["underlying"] == "PETR4"

    def test_forward_positions_per_share_calc(self, b3_forward_db):
        """forward_price_per_share = FwdPric / CurQty = 58828062.67 / 1358721 ≈ 43.30.

        Note: the task description said ≈43,32 (approximate); the exact value
        58828062.67 / 1358721 = 43.2999... rounds to 43.30.
        """
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["open_interest"] == 1196
        assert result["total_quantity"] == 1_358_721
        assert result["forward_price_aggregate"] == pytest.approx(58_828_062.67, rel=1e-6)
        # 58828062.67 / 1358721 = 43.2999... → rounded to 43.30
        assert result["forward_price_per_share"] == pytest.approx(43.30, abs=0.05)

    def test_forward_positions_instruments_join(self, b3_forward_db):
        """instruments.db join enriches with company, ISIN, security category."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["company"] == "PETROLEO BRASILEIRO S.A. PETROBRAS"
        assert result["isin"] == "BRPETRTNP008"
        assert result["security_category"] == "COMMON EQUITIES FORWARD"
        assert result["specification"] == "PN      N2"

    def test_forward_positions_accepts_bare_forward_segment(self, b3_forward_db):
        """ITUB4T has SgmtNm='FORWARD' (bare, no 'EQUITY' prefix) — still matches."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="ITUB4")
        assert result["status"] == "ok"
        assert result["ticker"] == "ITUB4T"
        assert result["company"] == "ITAÚ UNIBANCO HOLDING S.A."

    def test_forward_positions_zero_quantity(self, b3_forward_db):
        """BBSE3T has CurQty=0 → forward_price_per_share=None (avoid div by zero)."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="BBSE3")
        assert result["status"] == "ok"
        assert result["ticker"] == "BBSE3T"
        assert result["total_quantity"] == 0
        assert result["forward_price_per_share"] is None

    def test_forward_positions_filters_options(self, b3_forward_db):
        """PETRA201 (EQUITY CALL) is NOT a forward — should return not_found."""
        from data_sources.b3.api.query_engine import forward_positions
        # Construct 'PETRA201T' which doesn't exist as a forward.
        result = forward_positions(ticker="PETRA201")
        assert result["status"] == "not_found"
        assert result["ticker"] == "PETRA201T"

    def test_forward_positions_not_found(self, b3_forward_db):
        """forward_positions('XXXX') → not_found."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="XXXX")
        assert result["status"] == "not_found"

    def test_forward_positions_no_ticker(self, b3_forward_db):
        """forward_positions('') → error."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="")
        assert result["status"] == "error"

    def test_forward_positions_not_synced(self, tmp_path, monkeypatch):
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

        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4")
        assert result["status"] == "not_synced"

    def test_forward_positions_graceful_instruments_missing(self, tmp_path, monkeypatch):
        """If instruments.db is missing → derivatives data with instruments_ok=False."""
        from data_sources.b3.api.catalog import B3_TABLES

        b3_dir = tmp_path / "b3"
        b3_dir.mkdir(parents=True, exist_ok=True)

        # Build derivatives.db only (no instruments.db).
        deriv_path = b3_dir / B3_TABLES["derivatives"]["db_file"]
        conn = sqlite3.connect(str(deriv_path))
        conn.row_factory = sqlite3.Row
        deriv_cols = ["RptDt", "TckrSymb", "SgmtNm", "OpnIntrst", "CurQty", "FwdPric"]
        ensure_schema(conn, "derivatives", deriv_cols)
        conn.execute(
            "INSERT INTO derivatives (RptDt, TckrSymb, SgmtNm, OpnIntrst, CurQty, FwdPric, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-08-21", "PETR4T", "EQUITY FORWARD", "1.196", "1.358.721",
             "58828062,67", "2026-08-21T12:00:00"),
        )
        conn.execute(
            "INSERT INTO sync_state (table_name, date, synced_at, row_count, page_count) "
            "VALUES ('derivatives', '2026-08-21', '2026-08-21T12:00:00', 1, 1)"
        )
        conn.commit()
        conn.close()

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

        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4T"
        assert result["instruments_ok"] is False
        assert result["company"] == ""
        assert result["isin"] == ""
        assert result["security_category"] == ""
        assert result["specification"] == ""
        # Derivatives data still present.
        assert result["open_interest"] == 1196
        assert result["total_quantity"] == 1_358_721
        assert result["forward_price_per_share"] == pytest.approx(43.30, abs=0.05)

    def test_forward_positions_case_insensitive(self, b3_forward_db):
        """forward_positions('petr4') is case-insensitive."""
        from data_sources.b3.api.query_engine import forward_positions
        result = forward_positions(ticker="petr4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4T"


class TestForwardPositionsRoute:
    """Verify the b3/api route dispatcher exposes forward_positions."""

    def test_route_manifest_has_forward_positions(self):
        """MANIFEST['modes'] has the forward_positions mode."""
        from data_sources.b3.api import MANIFEST
        modes = MANIFEST["modes"]
        assert "forward_positions" in modes
        assert "ticker" in modes["forward_positions"]["params"]
        assert modes["forward_positions"]["include_in_all"] is False

    def test_route_dispatches_forward_positions(self, b3_forward_db):
        """route(mode='forward_positions', ticker='PETR4') returns the snapshot."""
        from data_sources.b3.api import route
        result = route("forward_positions", ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4T"

    def test_route_forward_positions_not_synced(self, tmp_path, monkeypatch):
        """route('forward_positions') returns not_synced when derivatives.db missing."""
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

        from data_sources.b3.api import route
        result = route("forward_positions", ticker="PETR4")
        assert result["status"] == "not_synced"
