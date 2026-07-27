"""tests/data_sources/cvm/bridge/test_sync.py -- Bridge sync_engine tests.

Tests cover:
  - sync_engine: per-ticker sync (check-fetched -> dividends -> CAD -> upsert)
  - ISIN fallback path (v1.1): dividends returns no codeCVM -> ISIN resolves CNPJ

Uses synthetic SQLite DBs in tmp_path. Never touches real data or network.
Dividends sync + CAD lookup are mocked (no HTTP calls).

Originally part of tests/data_sources/cvm/test_bridge.py; split as part of
test-reorg. Fixtures (bridge_db) come from conftest.py; helper functions come
from _helpers.py.
"""
from __future__ import annotations

import sqlite3

from tests.data_sources.cvm.bridge._helpers import (
    _insert_bridge_row,
    _mock_cad_miss,
    _mock_cad_ok,
    _mock_dividends_error,
    _mock_dividends_no_cvm,
    _mock_dividends_ok,
    _patch_cad,
    _patch_dividends,
    _patch_fca_miss,
)


# ════════════════════════════════════════════════════════════════════════════
# SYNC ENGINE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeSync:
    """Test bridge sync_engine.sync()."""

    def test_sync_single_ticker_success(self, bridge_db, monkeypatch):
        """Full success: dividends ok + CAD ok -> bridge.db has full row."""
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends+ISIN path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise dividends path
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
# ISIN FALLBACK TESTS (sync_engine v1.1)
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeISINFallback:
    """Test the ISIN fallback path in sync_engine (v1.1)."""

    def test_isin_fallback_success(self, bridge_db, monkeypatch):
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise ISIN path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise ISIN path
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
        _patch_fca_miss(monkeypatch)  # [v1.3] FCA not synced -> exercise ISIN path
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
