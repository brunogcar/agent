"""tests/skills/cvm/test_valuation.py -- Tests for the valuation skill.

Uses synthetic SQLite DBs (dfp, fre, trades) with realistic data.
Mocks the bridge resolver. No network.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm._db import _ensure_schema
from data_sources.cvm.fre.catalog import SCHEMA_SQL as FRE_SCHEMA


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_dfp_db(tmp_path):
    """Create synthetic DFP db with PETROBRAS annual data."""
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    # 2023 annual values (valor in thousands, escala='MIL')
    vals = {
        "3.11": 120000000,    # lucro líquido = 120 bi
        "2.03": 400000000,    # PL = 400 bi
        "3.05": 200000000,    # EBIT = 200 bi
        "6.01": 180000000,    # FCO = 180 bi
        "1.01.01": 34000000,  # Caixa = 34 bi
        "2.01.04": 66000000,  # Dívida circulante = 66 bi
        "2.02.01": 305000000, # Dívida não-circulante = 305 bi
        "7.08.04": 60000000,  # Proventos = 60 bi
    }
    for code, val in vals.items():
        grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (1, ?, ?, ?, 1, '2023-01-01', '2023-12-31', 12, 'ÚLTIMO', 1, ?, 'MIL')",
            (code, f"Account {code}", grupo, val))
    conn.commit()
    conn.close()
    return db_path


def _make_fre_db(tmp_path):
    """Create synthetic FRE db with share counts."""
    db_path = tmp_path / "fre.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(FRE_SCHEMA)
    conn.execute(
        "INSERT INTO distribuicao_capital (cnpj, data_referencia, versao, nome_companhia, "
        "qtd_on_circulacao, qtd_pn_circulacao, qtd_total_circulacao) "
        "VALUES ('33000167000101', '2023-12-31', 1, 'PETROLEO BRASILEIRO S.A.', "
        "7442231382, 5446501379, 12888732761)")
    conn.commit()
    conn.close()
    return db_path


def _make_trades_db(tmp_path):
    """Create synthetic b3 trades.db with latest PETR4 price."""
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE trades (
            RptDt TEXT, TckrSymb TEXT, SgmtNm TEXT,
            MinPric REAL, MaxPric REAL, TradAvrgPric REAL, LastPric REAL,
            OscnPctg REAL, AdjstdQt REAL, TradQty REAL, NtlFinVol REAL
        )
    """)
    conn.execute("""
        CREATE TABLE sync_state (
            table_name TEXT, date TEXT, synced_at TEXT, row_count INTEGER,
            last_page INTEGER DEFAULT 0, page_count INTEGER DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO trades (RptDt, TckrSymb, LastPric, OscnPctg, NtlFinVol) "
        "VALUES ('2026-07-24', 'PETR4', 38.50, 1.23, 5000000000)")
    conn.execute(
        "INSERT INTO sync_state (table_name, date, synced_at, row_count) "
        "VALUES ('trades', '2026-07-24', '2026-07-24T10:00:00', 1)")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def valuation_env(tmp_path, monkeypatch):
    """Set up synthetic DFP + FRE + trades DBs + bridge mock."""
    dfp_path = _make_dfp_db(tmp_path)
    fre_path = _make_fre_db(tmp_path)
    trades_path = _make_trades_db(tmp_path)
    bridge_path = tmp_path / "bridge.db"

    # Create bridge.db with PETR4 mapping
    from data_sources.cvm.bridge.catalog import SCHEMA_SQL as BRIDGE_SCHEMA
    bconn = sqlite3.connect(str(bridge_path))
    bconn.executescript(BRIDGE_SCHEMA)
    bconn.execute(
        "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
        "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
        "VALUES ('PETR4', 'PETR', '9512', 'PETROBRAS', '33000167000101', "
        "'PETROLEO BRASILEIRO S.A.', 'PETROBRAS', 'ATIVO', 'Petróleo', 'Bolsa', '2024-01-01')")
    bconn.commit()
    bconn.close()

    def mock_connect_dfp(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(dfp_path))
        c.row_factory = sqlite3.Row
        return c

    def mock_connect_fre(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{fre_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(fre_path))
        c.row_factory = sqlite3.Row
        return c

    def mock_b3_db_path(table_name):
        if table_name == "trades":
            return trades_path
        return tmp_path / f"{table_name}.db"

    monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
    monkeypatch.setattr("data_sources.cvm._db.connect_fre", mock_connect_fre)
    monkeypatch.setattr("data_sources.cvm._db.dfp_db_path", lambda: dfp_path)
    monkeypatch.setattr("data_sources.cvm._db.fre_db_path", lambda: fre_path)
    monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", lambda: bridge_path)
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", lambda: bridge_path)
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.b3.api.catalog.db_path", mock_b3_db_path)
    # Disable auto-sync (bridge is already populated in tests)
    monkeypatch.setattr("data_sources.cvm._bridge._auto_sync_bridge", lambda ticker: True)
    # [v1.0.2] Mock investsite price fetcher (primary source) to use b3 trades data
    # In tests, we want b3 trades to be the price source (deterministic)
    def mock_get_price_investsite(ticker):
        return {"status": "error", "error": "investsite mocked out in tests"}
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation._get_price_investsite",
        mock_get_price_investsite)
    # [v1.0.5] Mock investsite shares fetcher (fallback) — FRE is our primary in tests
    def mock_get_shares_investsite(ticker):
        return {"status": "error", "error": "investsite mocked out in tests"}
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation._get_shares_investsite",
        mock_get_shares_investsite)

    return dfp_path, fre_path, trades_path, bridge_path


# ════════════════════════════════════════════════════════════════════════════
# RATIOS MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestRatiosMode:

    def test_ratios_ok(self, valuation_env):
        from skills.cvm.valuation.valuation import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"

        r = result["ratios"]
        # Price from trades.db
        assert r["price"] == 38.50
        # Shares from fre.db (12.888.732.761)
        assert r["total_shares"] == 12888732761
        # Market Cap = 38.50 × 12.888.732.761 ≈ 496 billion
        assert r["market_cap"] is not None
        assert r["market_cap"] > 400_000_000_000  # > 400B

        # EPS = 120B / 12.88B shares ≈ 9.31
        assert r["eps"] is not None
        assert 9.0 < r["eps"] < 10.0

        # P/L = 38.50 / 9.31 ≈ 4.13
        assert r["p_l"] is not None
        assert 3.5 < r["p_l"] < 4.5

        # VPA = 400B / 12.88B ≈ 31.04
        assert r["vpa"] is not None
        assert 30.0 < r["vpa"] < 32.0

        # P/VPA = 38.50 / 31.04 ≈ 1.24
        assert r["p_vpa"] is not None
        assert 1.15 < r["p_vpa"] < 1.30

        # EV = Market Cap + Debt - Cash
        # Debt = 66B + 305B = 371B, Cash = 34B
        assert r["ev"] is not None

        # P/EBIT = 38.50 / (200B / 12.88B)
        assert r["p_ebit"] is not None

        # Dividend Yield = (60B / 12.88B) / 38.50
        assert r["dividend_yield"] is not None
        assert 0.05 < r["dividend_yield"] < 0.15  # ~6-15%

    def test_ratios_no_company(self, valuation_env):
        from skills.cvm.valuation.valuation import ratios
        result = ratios()
        assert result["status"] == "error"

    def test_ratios_invalid_ticker(self, valuation_env):
        from skills.cvm.valuation.valuation import ratios
        result = ratios(company="!!!")
        assert result["status"] == "error"

    def test_ratios_missing_price(self, valuation_env, monkeypatch):
        """If both investsite and trades.db unavailable, return error."""
        # investsite already mocked to error in fixture
        monkeypatch.setattr(
            "data_sources.b3.api.catalog.db_path",
            lambda table: Path("/nonexistent/trades.db"))
        from skills.cvm.valuation.valuation import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"  # outer status ok
        assert result["ratios"]["status"] == "error"
        assert "Price unavailable" in result["ratios"]["error"]


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryMode:

    def test_summary_ok(self, valuation_env):
        from skills.cvm.valuation.valuation import summary
        result = summary(company="PETR4")
        assert result["status"] == "ok"
        assert "ratios" in result
        assert "data_availability" in result
        assert result["data_availability"]["price"] == "ok"
        assert result["data_availability"]["dfp_annual"] == "ok"
        assert result["data_availability"]["fre_shares"] == "ok"

    def test_summary_no_company(self, valuation_env):
        from skills.cvm.valuation.valuation import summary
        result = summary()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestValuationRoute:

    def test_route_no_mode(self):
        from skills.cvm.valuation import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.cvm.valuation import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_ratios(self, valuation_env):
        from skills.cvm.valuation import route
        result = route(mode="ratios", company="PETR4")
        assert result["status"] == "ok"


# ════════════════════════════════════════════════════════════════════════════
# BR_VALIDATOR TESTS (for the updated parse_brl + new functions)
# ════════════════════════════════════════════════════════════════════════════

class TestBrValidator:

    def test_parse_brl_suffixes(self):
        from core.br_validator import parse_brl
        assert parse_brl("R$ 596,36 B") == 596360000000.0
        assert parse_brl("R$ 1,25 T") == 1250000000000.0
        assert parse_brl("R$ 50,00 M") == 50000000.0

    def test_parse_brl_percentage(self):
        from core.br_validator import parse_brl
        assert parse_brl("27,18%") == 0.2718

    def test_parse_brl_plain(self):
        from core.br_validator import parse_brl
        assert parse_brl("5,15") == 5.15
        assert parse_brl("1.234,56") == 1234.56
        assert parse_brl("-R$ 50,00") == -50.0

    def test_parse_percentage(self):
        from core.br_validator import parse_percentage
        assert parse_percentage("27,18%") == 27.18
        assert parse_percentage("27,18%", as_decimal=True) == 0.2718

    def test_format_brl(self):
        from core.br_validator import format_brl
        assert "B" in format_brl(596360000000.0)
        assert "T" in format_brl(1250000000000.0)
        assert "5,15" in format_brl(5.15)

    def test_parse_escala(self):
        from core.br_validator import parse_escala
        assert parse_escala("MIL") == 1000.0
        assert parse_escala("MILHOES") == 1000000.0
        assert parse_escala("UNIDADE") == 1.0
        assert parse_escala(None) == 1.0
        assert parse_escala("") == 1.0

    def test_validate_ticker(self):
        from core.br_validator import validate_ticker
        assert validate_ticker("petr4") == "PETR4"
        assert validate_ticker("VALE3") == "VALE3"
