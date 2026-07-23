"""tests/data_sources/cvm/test_bridge.py -- Tests for the B3-CVM bridge.

Tests cover:
  - sync_engine: per-ticker sync (check-fetched -> dividends -> CAD -> upsert)
  - query_engine: lookup / status / resolve
  - _bridge.py resolver: ticker -> (cnpj, cd_cvm) -> empresas, with cd_cvm fallback

Uses synthetic SQLite DBs in tmp_path. Never touches real data or network.
Dividends sync + CAD lookup are mocked (no HTTP calls).
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

from data_sources.cvm.bridge.catalog import SCHEMA_SQL


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def bridge_db(tmp_path, monkeypatch):
    """Create an empty bridge.db and patch catalog to use it."""
    db_path = tmp_path / "bridge.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
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

    monkeypatch.setattr("data_sources.cvm.bridge.catalog.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.cvm.bridge.catalog.connect", mock_connect)
    monkeypatch.setattr("data_sources.cvm.bridge.query_engine.db_path", mock_db_path)
    monkeypatch.setattr("data_sources.cvm.bridge.query_engine.connect", mock_connect)
    # sync_engine binds `connect` + `ensure_schema` at import time from catalog,
    # so patch its own namespace too.
    monkeypatch.setattr("data_sources.cvm.bridge.sync_engine.connect", mock_connect)
    # _bridge.py binds `bridge_db_path` at import time from _db.
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", mock_db_path)
    monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", mock_db_path)
    return db_path


def _insert_bridge_row(db_path, ticker, issuing, cd_cvm, trading_name, cnpj,
                       denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at):
    """Helper to insert a row directly into bridge.db."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
        "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ticker, issuing, cd_cvm, trading_name, cnpj, denom_social,
         denom_comerc, sit, setor_ativ, tp_merc, synced_at),
    )
    conn.commit()
    conn.close()


# ── Mock factories for dividends + CAD ───────────────────────────────────────

def _mock_dividends_ok(code_cvm, trading_name="TESTCO"):
    """Return a mock for dividends sync + company_info that succeeds."""
    def mock_sync(ticker="", force=False, trace_id=""):
        return {"status": "ok", "ticker": ticker, "cash_count": 1,
                "stock_count": 0, "sub_count": 0}
    def mock_company_info(ticker=""):
        return {"status": "ok", "ticker": ticker,
                "info": {"code_cvm": code_cvm, "trading_name": trading_name}}
    return mock_sync, mock_company_info


def _mock_dividends_no_cvm():
    """Dividends sync succeeds but company_info has no codeCVM."""
    def mock_sync(ticker="", force=False, trace_id=""):
        return {"status": "ok", "ticker": ticker}
    def mock_company_info(ticker=""):
        return {"status": "ok", "ticker": ticker,
                "info": {"code_cvm": "", "trading_name": "NO-CVM-CO"}}
    return mock_sync, mock_company_info


def _mock_dividends_error():
    """Dividends sync returns error."""
    def mock_sync(ticker="", force=False, trace_id=""):
        return {"status": "error", "ticker": ticker, "error": "API down"}
    def mock_company_info(ticker=""):
        return {"status": "not_found", "ticker": ticker}
    return mock_sync, mock_company_info


def _mock_cad_ok(cnpj, denom_social, denom_comerc, sit="ATIVO",
                 setor_ativ="Petróleo", tp_merc="Bolsa", cd_cvm_val="9512"):
    """CAD lookup succeeds. Includes CD_CVM (needed by ISIN fallback path).

    NOTE: uses **kwargs so any combination of cnpj/cd_cvm/name keyword args
    from the real lookup() signature works without TypeError.
    """
    def mock_lookup(**kwargs):
        return {"status": "ok", "company": {
            "CNPJ_CIA": cnpj, "DENOM_SOCIAL": denom_social,
            "DENOM_COMERC": denom_comerc, "SIT": sit,
            "SETOR_ATIV": setor_ativ, "TP_MERC": tp_merc,
            "CD_CVM": cd_cvm_val,
        }}
    return mock_lookup


def _mock_cad_miss():
    """CAD lookup returns not_found."""
    def mock_lookup(**kwargs):
        return {"status": "not_found"}
    return mock_lookup


def _patch_dividends(monkeypatch, mock_sync, mock_company_info):
    monkeypatch.setattr("data_sources.b3.dividends.sync_engine.sync", mock_sync)
    monkeypatch.setattr("data_sources.b3.dividends.query_engine.company_info", mock_company_info)


def _patch_cad(monkeypatch, mock_lookup):
    monkeypatch.setattr("data_sources.cvm.cad.query_engine.lookup", mock_lookup)


# ════════════════════════════════════════════════════════════════════════════
# SYNC ENGINE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeSync:
    """Test bridge sync_engine.sync()."""

    def test_sync_single_ticker_success(self, bridge_db, monkeypatch):
        """Full success: dividends ok + CAD ok -> bridge.db has full row."""
        m_sync, m_info = _mock_dividends_ok("9512", "PETROBRAS")
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_ok(
            "33000167000101", "PETROLEO BRASILEIRO S.A.", "PETROBRAS"))

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"
        assert result["cd_cvm"] == "9512"
        assert result["cnpj"] == "33000167000101"
        assert result["denom_social"] == "PETROLEO BRASILEIRO S.A."

        # Verify the row landed in bridge.db
        conn = sqlite3.connect(str(bridge_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ticker_map WHERE ticker='PETR4'").fetchone()
        conn.close()
        assert row is not None
        assert row["cd_cvm"] == "9512"
        assert row["cnpj"] == "33000167000101"
        assert row["issuing"] == "PETR"
        assert row["denom_social"] == "PETROLEO BRASILEIRO S.A."
        assert row["sit"] == "ATIVO"

    def test_sync_skips_already_bridged(self, bridge_db, monkeypatch):
        """Ticker already in bridge.db (not force) -> skipped."""
        _insert_bridge_row(bridge_db, "PETR4", "PETR", "9512", "PETROBRAS",
                           "33000167000101", "PETROLEO BRASILEIRO S.A.",
                           "PETROBRAS", "ATIVO", "Petróleo", "Bolsa", "2024-01-01")

        # Even if dividends/CAD are broken, sync should skip without calling them
        call_count = {"n": 0}
        def mock_sync(ticker="", force=False, trace_id=""):
            call_count["n"] += 1
            return {"status": "ok"}
        _patch_dividends(monkeypatch, mock_sync, lambda ticker="": {"status": "ok"})
        _patch_cad(monkeypatch, _mock_cad_miss())

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "skipped"
        assert result["reason"] == "already in bridge"
        assert call_count["n"] == 0  # dividends NOT called

    def test_sync_force_re_fetches(self, bridge_db, monkeypatch):
        """force=True re-fetches even if already in bridge.db."""
        _insert_bridge_row(bridge_db, "PETR4", "PETR", "OLD", "OLDNAME",
                           "00000000000000", "OLD", "OLD", "ATIVO", "", "", "2020-01-01")

        m_sync, m_info = _mock_dividends_ok("9512", "PETROBRAS")
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_ok(
            "33000167000101", "PETROLEO BRASILEIRO S.A.", "PETROBRAS"))

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4", force=True)

        assert result["status"] == "ok"
        assert result["cd_cvm"] == "9512"  # updated from "OLD"

        conn = sqlite3.connect(str(bridge_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ticker_map WHERE ticker='PETR4'").fetchone()
        conn.close()
        assert row["cd_cvm"] == "9512"
        assert row["cnpj"] == "33000167000101"

    def test_sync_no_code_cvm(self, bridge_db, monkeypatch):
        """Dividends ok but no codeCVM -> 'no_cvm' logged, partial row."""
        m_sync, m_info = _mock_dividends_no_cvm()
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_ok(
            "33000167000101", "X", "Y"))

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="ZZZZ4")

        assert result["status"] == "error"
        assert "no codeCVM" in result["error"]

        conn = sqlite3.connect(str(bridge_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ticker_map WHERE ticker='ZZZZ4'").fetchone()
        log = conn.execute("SELECT * FROM sync_log WHERE ticker='ZZZZ4'").fetchone()
        conn.close()
        assert row is not None
        assert row["cd_cvm"] == ""
        assert log["action"] == "no_cvm"

    def test_sync_cad_miss(self, bridge_db, monkeypatch):
        """Dividends returns codeCVM but CAD doesn't have it -> 'no_cad', partial."""
        m_sync, m_info = _mock_dividends_ok("99999", "UNKNOWN")
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_miss())

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="UNKW4")

        assert result["status"] == "ok"
        assert result["cd_cvm"] == "99999"
        assert result["cnpj"] == ""
        assert "not in cad.db" in result["warning"]

        conn = sqlite3.connect(str(bridge_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ticker_map WHERE ticker='UNKW4'").fetchone()
        log = conn.execute("SELECT * FROM sync_log WHERE ticker='UNKW4'").fetchone()
        conn.close()
        assert row["cd_cvm"] == "99999"
        assert row["cnpj"] == ""
        assert log["action"] == "no_cad"

    def test_sync_dividends_error(self, bridge_db, monkeypatch):
        """Dividends sync fails -> bridge tries ISIN fallback -> if that fails too, error."""
        m_sync, m_info = _mock_dividends_error()
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_ok("x", "y", "z"))
        # Mock dividends query (used by _get_isin_from_dividends) to return no ISIN
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends",
            lambda ticker="", limit=50: {"status": "not_found", "dividends": []})
        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "error"
        # After ISIN fallback attempt, step is 'dividends+isin'
        assert result["step"] == "dividends+isin"

    def test_sync_multiple_tickers(self, bridge_db, monkeypatch):
        """List of tickers -> aggregated results."""
        m_sync, m_info = _mock_dividends_ok("9512", "PETROBRAS")
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_ok(
            "33000167000101", "PETROLEO BRASILEIRO S.A.", "PETROBRAS"))

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(tickers=["PETR4", "PETR3"])

        assert result["status"] == "ok"
        assert result["total"] == 2
        assert result["linked"] == 2
        assert "PETR4" in result["results"]
        assert "PETR3" in result["results"]
        assert result["results"]["PETR4"]["status"] == "ok"

    def test_sync_no_ticker(self, bridge_db):
        """No ticker or tickers -> error."""
        from data_sources.cvm.bridge.sync_engine import sync
        result = sync()
        assert result["status"] == "error"

    def test_sync_cad_file_not_found(self, bridge_db, monkeypatch):
        """CAD raises FileNotFoundError -> treated as 'no_cad' (graceful)."""
        m_sync, m_info = _mock_dividends_ok("9512", "PETROBRAS")
        _patch_dividends(monkeypatch, m_sync, m_info)
        def mock_lookup(cnpj="", cd_cvm="", name="", full=False):
            raise FileNotFoundError("cad.db not found")
        _patch_cad(monkeypatch, mock_lookup)

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "ok"
        assert result["cd_cvm"] == "9512"
        assert result["cnpj"] == ""  # no CNPJ, but cd_cvm stored

    def test_sync_normalizes_ticker_case(self, bridge_db, monkeypatch):
        """Lowercase ticker is normalized to uppercase."""
        m_sync, m_info = _mock_dividends_ok("9512", "PETROBRAS")
        _patch_dividends(monkeypatch, m_sync, m_info)
        _patch_cad(monkeypatch, _mock_cad_ok(
            "33000167000101", "PETROLEO BRASILEIRO S.A.", "PETROBRAS"))

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="petr4")

        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"


# ════════════════════════════════════════════════════════════════════════════
# QUERY ENGINE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeISINFallback:
    """Test the ISIN fallback path in sync_engine (v1.1)."""

    def test_isin_fallback_success(self, bridge_db, monkeypatch):
        """Dividends returns no codeCVM -> ISIN fallback resolves CNPJ -> CAD by cnpj."""
        # Dividends: ok but no codeCVM
        m_sync, m_info = _mock_dividends_no_cvm()
        _patch_dividends(monkeypatch, m_sync, m_info)

        # Mock dividends query to return an ISIN (for _get_isin_from_dividends)
        def mock_dividends_query(ticker="", limit=50):
            return {"status": "ok", "ticker": ticker,
                    "dividends": [{"isin_code": "BRPETRACNPR6"}]}
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", mock_dividends_query)

        # Mock isin_fetcher.sync + lookup_isin
        monkeypatch.setattr(
            "data_sources.cvm.bridge.isin_fetcher.sync",
            lambda force=False, trace_id="": {"status": "ok", "entries": 300000})
        monkeypatch.setattr(
            "data_sources.cvm.bridge.isin_fetcher.lookup_isin",
            lambda isin: "33000167000101" if isin == "BRPETRACNPR6" else None)

        # CAD lookup by cnpj succeeds (cd_cvm=9512)
        _patch_cad(monkeypatch, _mock_cad_ok(
            "33.000.167/0001-01", "PETROLEO BRASILEIRO S.A.", "PETROBRAS"))

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "ok"
        assert result["source"] == "isin_fallback"
        assert result["cnpj"] == "33000167000101"
        assert result["cd_cvm"] == "9512"
        assert "PETROLEO" in result["denom_social"]

        # Verify sync_log recorded 'linked_isin'
        conn = sqlite3.connect(str(bridge_db))
        conn.row_factory = sqlite3.Row
        log = conn.execute("SELECT * FROM sync_log WHERE ticker='PETR4'").fetchone()
        conn.close()
        assert log["action"] == "linked_isin"

    def test_isin_fallback_no_isin_in_dividends(self, bridge_db, monkeypatch):
        """Dividends returns no codeCVM + no ISIN in dividends.db -> ISIN fallback fails."""
        m_sync, m_info = _mock_dividends_no_cvm()
        _patch_dividends(monkeypatch, m_sync, m_info)

        # No ISIN in dividends query
        def mock_dividends_query(ticker="", limit=50):
            return {"status": "not_found", "ticker": ticker, "dividends": []}
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", mock_dividends_query)

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "error"
        assert "ISIN fallback failed" in result["error"] or "no codeCVM" in result["error"]

    def test_isin_fallback_cad_miss(self, bridge_db, monkeypatch):
        """ISIN resolves CNPJ but CAD doesn't have it -> store ticker+cnpj, no_cad."""
        m_sync, m_info = _mock_dividends_no_cvm()
        _patch_dividends(monkeypatch, m_sync, m_info)

        def mock_dividends_query(ticker="", limit=50):
            return {"status": "ok", "ticker": ticker,
                    "dividends": [{"isin_code": "BRPETRACNPR6"}]}
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", mock_dividends_query)

        monkeypatch.setattr(
            "data_sources.cvm.bridge.isin_fetcher.sync",
            lambda force=False, trace_id="": {"status": "ok", "entries": 300000})
        monkeypatch.setattr(
            "data_sources.cvm.bridge.isin_fetcher.lookup_isin",
            lambda isin: "33000167000101")

        # CAD miss for this CNPJ
        _patch_cad(monkeypatch, _mock_cad_miss())

        from data_sources.cvm.bridge.sync_engine import sync
        result = sync(ticker="PETR4")

        assert result["status"] == "ok"
        assert result["source"] == "isin_fallback"
        assert result["cnpj"] == "33000167000101"
        assert result["cd_cvm"] == ""
        assert "CAD miss" in result["warning"]


class TestBridgeQuery:
    """Test bridge query_engine."""

    @pytest.fixture
    def populated_bridge(self, bridge_db):
        """Bridge.db with 3 test tickers."""
        _insert_bridge_row(bridge_db, "PETR4", "PETR", "9512", "PETROBRAS",
                           "33000167000101", "PETROLEO BRASILEIRO S.A.",
                           "PETROBRAS", "ATIVO", "Petróleo", "Bolsa", "2024-01-01")
        _insert_bridge_row(bridge_db, "VALE3", "VALE", "4170", "VALE",
                           "33592510000154", "VALE S.A.", "VALE",
                           "ATIVO", "Mineração", "Bolsa", "2024-01-01")
        _insert_bridge_row(bridge_db, "UNKW4", "UNKW", "99999", "UNKNOWN",
                           "", "UNKNOWN", "UNKNOWN", "", "", "", "2024-01-01")
        return bridge_db

    def test_lookup_by_ticker(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import lookup
        result = lookup(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["cd_cvm"] == "9512"
        assert result["cnpj"] == "33000167000101"
        assert result["denom_social"] == "PETROLEO BRASILEIRO S.A."

    def test_lookup_by_cnpj(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import lookup
        result = lookup(cnpj="33000167000101")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"

    def test_lookup_by_cnpj_formatted(self, populated_bridge):
        """Formatted CNPJ is normalized to digits."""
        from data_sources.cvm.bridge.query_engine import lookup
        result = lookup(cnpj="33.000.167/0001-01")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"

    def test_lookup_by_cd_cvm(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import lookup
        result = lookup(cd_cvm="4170")
        assert result["status"] == "ok"
        assert result["ticker"] == "VALE3"

    def test_lookup_not_found(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import lookup
        result = lookup(ticker="XXXX4")
        assert result["status"] == "not_found"

    def test_lookup_no_args(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import lookup
        result = lookup()
        assert result["status"] == "error"

    def test_status(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import status
        result = status()
        assert result["status"] == "ok"
        assert result["total_tickers"] == 3
        assert result["with_cnpj"] == 2  # UNKW4 has no cnpj
        assert result["with_cd_cvm"] == 3
        assert result["cnpj_coverage_pct"] == 66.7

    def test_status_not_synced(self, tmp_path, monkeypatch):
        """bridge.db doesn't exist -> not_synced."""
        monkeypatch.setattr("data_sources.cvm.bridge.query_engine.db_path",
                            lambda: tmp_path / "nonexistent.db")
        monkeypatch.setattr("data_sources.cvm.bridge.catalog.db_path",
                            lambda: tmp_path / "nonexistent.db")
        from data_sources.cvm.bridge.query_engine import status
        result = status()
        assert result["status"] == "not_synced"

    def test_resolve_name(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import resolve
        result = resolve(query="petro")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["matches"][0]["ticker"] == "PETR4"

    def test_resolve_multiple(self, populated_bridge):
        """Search that matches multiple tickers."""
        from data_sources.cvm.bridge.query_engine import resolve
        result = resolve(query="VALE")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["matches"][0]["ticker"] == "VALE3"

    def test_resolve_not_found(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import resolve
        result = resolve(query="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_resolve_short_query(self, populated_bridge):
        from data_sources.cvm.bridge.query_engine import resolve
        result = resolve(query="a")
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# RESOLVER (_bridge.py) TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeResolver:
    """Test _bridge.py resolve_company with the new ticker_map table."""

    @pytest.fixture
    def dfp_with_bridge(self, tmp_path, monkeypatch):
        """Create a synthetic DFP db + bridge.db, patch all paths."""
        # DFP db
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        from data_sources.cvm._db import _ensure_schema
        _ensure_schema(conn)
        # PETROBRAS: cnpj=33000167000101, cd_cvm=9512
        conn.execute(
            "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
            "VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')"
        )
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor) "
            "VALUES (1, '1', 'Ativo Total', 'BPA', 1, '', '2023-12-31', 12, 'ÚLTIMO', 1, 100000)"
        )
        conn.commit()
        conn.close()

        # Bridge db with PETR4 -> cnpj + cd_cvm
        bridge_path = tmp_path / "bridge.db"
        conn = sqlite3.connect(str(bridge_path))
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
            "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
            "VALUES ('PETR4', 'PETR', '9512', 'PETROBRAS', '33000167000101', "
            "'PETROLEO BRASILEIRO S.A.', 'PETROBRAS', 'ATIVO', 'Petróleo', 'Bolsa', '2024-01-01')"
        )
        conn.commit()
        conn.close()

        # Patch DFP paths
        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c
        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm.dfp.query_engine.connect_dfp", mock_connect_dfp)

        # Patch bridge path to our synthetic bridge.db
        # _bridge.py binds bridge_db_path at import time, so patch its namespace.
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", lambda: bridge_path)

        # Prevent CAD from interfering
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))
        return dfp_path

    def test_resolver_ticker_via_cnpj(self, dfp_with_bridge):
        """Ticker resolves via bridge cnpj -> empresas."""
        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            ids, name = resolve_company(conn, "PETR4")
            assert ids == [1]
            assert "PETROLEO" in name
        finally:
            conn.close()

    def test_resolver_ticker_lowercase(self, dfp_with_bridge):
        """Lowercase ticker is handled by looks_like_ticker (uppercased)."""
        from data_sources.cvm._bridge import resolve_company, looks_like_ticker
        assert looks_like_ticker("petr4") is True
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            ids, name = resolve_company(conn, "petr4")
            assert ids == [1]
        finally:
            conn.close()

    def test_resolver_ticker_cd_cvm_fallback(self, tmp_path, monkeypatch):
        """Bridge has cd_cvm but NO cnpj -> resolver falls back to cd_cvm."""
        # DFP db with company matched by cd_cvm only
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        from data_sources.cvm._db import _ensure_schema
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
            "VALUES (5, '99999999999999', 'MYSTERY CO', 2023, '55555')"
        )
        conn.commit()
        conn.close()

        # Bridge db: ticker has cd_cvm='55555' but empty cnpj
        bridge_path = tmp_path / "bridge.db"
        conn = sqlite3.connect(str(bridge_path))
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
            "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
            "VALUES ('MYST4', 'MYST', '55555', 'MYSTERY', '', '', '', '', '', '', '2024-01-01')"
        )
        conn.commit()
        conn.close()

        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c
        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))

        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            ids, name = resolve_company(conn, "MYST4")
            assert ids == [5]
            assert "MYSTERY" in name
        finally:
            conn.close()

    def test_resolver_ticker_not_in_bridge_no_auto_sync(self, dfp_with_bridge, monkeypatch):
        """Ticker not in bridge + auto_sync=False -> falls through, no sync."""
        # Track if bridge sync was called
        sync_called = {"n": 0}
        def mock_sync(ticker="", **kw):
            sync_called["n"] += 1
            return {"status": "ok"}
        monkeypatch.setattr("data_sources.cvm._bridge._auto_sync_bridge", mock_sync)

        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            ids, name = resolve_company(conn, "WWWW4", auto_sync=False)
            assert ids == []
            assert sync_called["n"] == 0  # auto-sync NOT called
        finally:
            conn.close()

    def test_resolver_auto_sync_on_demand(self, tmp_path, monkeypatch):
        """[v1.2] Ticker not in bridge + auto_sync=True -> auto-sync -> retry -> found."""
        # DFP db with PETROBRAS
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        from data_sources.cvm._db import _ensure_schema
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
            "VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
        conn.commit()
        conn.close()

        # bridge.db starts EMPTY (ticker not present)
        bridge_path = tmp_path / "bridge.db"
        conn = sqlite3.connect(str(bridge_path))
        from data_sources.cvm.bridge.catalog import SCHEMA_SQL
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c
        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))

        # Mock _auto_sync_bridge to INSERT the ticker into bridge.db (simulating
        # a successful sync), then return True
        def mock_auto_sync(ticker):
            bconn = sqlite3.connect(str(bridge_path))
            bconn.execute(
                "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
                "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ticker, ticker[:4], "9512", "PETROBRAS", "33000167000101",
                 "PETROLEO BRASILEIRO S.A.", "PETROBRAS", "ATIVO", "Petróleo",
                 "Bolsa", "2024-01-01"))
            bconn.commit()
            bconn.close()
            return True
        monkeypatch.setattr("data_sources.cvm._bridge._auto_sync_bridge", mock_auto_sync)

        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            # First call: ticker not in bridge -> auto-sync -> retry -> found
            ids, name = resolve_company(conn, "PETR4", auto_sync=True)
            assert ids == [1]
            assert "PETROLEO" in name
        finally:
            conn.close()

    def test_resolver_auto_sync_fails_gracefully(self, tmp_path, monkeypatch):
        """Auto-sync fails (network error) -> resolver falls through, no crash."""
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        from data_sources.cvm._db import _ensure_schema
        _ensure_schema(conn)
        conn.commit()
        conn.close()

        bridge_path = tmp_path / "bridge.db"
        conn = sqlite3.connect(str(bridge_path))
        from data_sources.cvm.bridge.catalog import SCHEMA_SQL
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c
        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))
        # Auto-sync returns False (failed)
        monkeypatch.setattr("data_sources.cvm._bridge._auto_sync_bridge",
                            lambda ticker: False)

        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            ids, name = resolve_company(conn, "PETR4", auto_sync=True)
            assert ids == []  # not found, but no crash
        finally:
            conn.close()

    def test_resolver_no_bridge_db(self, tmp_path, monkeypatch):
        """bridge.db doesn't exist -> _resolve_via_bridge returns (None, None)."""
        nonexistent = tmp_path / "nonexistent.db"
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                            lambda: nonexistent)
        from data_sources.cvm._bridge import _resolve_via_bridge
        cnpj, cd_cvm = _resolve_via_bridge("PETR4")
        assert cnpj is None
        assert cd_cvm is None

    def test_resolver_formatted_cnpj_in_dfp(self, tmp_path, monkeypatch):
        """[v1.2.1] DFP stores CNPJ formatted ('33.000.167/0001-01') but bridge
        has normalized ('33000167000101'). Resolver must match both via REPLACE.

        This is the exact bug that caused WEGE3 -> not_found: the bridge correctly
        resolved the ticker to a normalized CNPJ, but dfp.db.empresas had the
        formatted CNPJ from the raw CVM CSV.
        """
        # DFP db with FORMATTED cnpj (as stored by pre-v1.2.1 sync)
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        from data_sources.cvm._db import _ensure_schema
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
            "VALUES (1, '33.000.167/0001-01', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
        conn.commit()
        conn.close()

        # Bridge db with NORMALIZED cnpj (as stored by bridge sync)
        bridge_path = tmp_path / "bridge.db"
        conn = sqlite3.connect(str(bridge_path))
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
            "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
            "VALUES ('PETR4', 'PETR', '9512', 'PETROBRAS', '33000167000101', "
            "'PETROLEO BRASILEIRO S.A.', 'PETROBRAS', 'ATIVO', 'Petróleo', 'Bolsa', '2024-01-01')")
        conn.commit()
        conn.close()

        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c
        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._db.bridge_db_path", lambda: bridge_path)
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))

        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            # Bridge has normalized CNPJ, dfp.db has formatted CNPJ — must still match
            ids, name = resolve_company(conn, "PETR4", auto_sync=False)
            assert ids == [1], f"Expected [1], got {ids} — CNPJ format mismatch not handled"
            assert "PETROLEO" in name
        finally:
            conn.close()

    def test_resolver_direct_cnpj_query_formatted_db(self, tmp_path, monkeypatch):
        """[v1.2.1] Direct CNPJ query ('33000167000101') must also match formatted
        CNPJ in dfp.db ('33.000.167/0001-01') via REPLACE."""
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        from data_sources.cvm._db import _ensure_schema
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
            "VALUES (1, '33.000.167/0001-01', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
        conn.commit()
        conn.close()

        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c
        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                            lambda: tmp_path / "nonexistent.db")
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))

        from data_sources.cvm._bridge import resolve_company
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        try:
            # Query by normalized CNPJ, db has formatted — must match
            ids, name = resolve_company(conn, "33000167000101", auto_sync=False)
            assert ids == [1]
            assert "PETROLEO" in name
        finally:
            conn.close()


# ════════════════════════════════════════════════════════════════════════════
# ESCALA PARSER TESTS (v1.2.1)
# ════════════════════════════════════════════════════════════════════════════

class TestParseEscala:
    """Test the parse_escala helper (v1.2.1)."""

    def test_mil(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("MIL") == 1000.0

    def test_milhoes(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("MILHOES") == 1000000.0

    def test_unidade(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("UNIDADE") == 1.0

    def test_empty(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("") == 1.0

    def test_none(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala(None) == 1.0

    def test_lowercase(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("mil") == 1000.0

    def test_numeric_string(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("1000") == 1000.0

    def test_unknown_returns_unit(self):
        from data_sources.cvm._db import parse_escala
        assert parse_escala("UNKNOWN") == 1.0
