"""tests/data_sources/cvm/bridge/test_query.py -- Bridge query_engine tests.

Tests cover:
  - query_engine: lookup (by ticker / cnpj / cd_cvm) + status + resolve

Uses the `populated_bridge` fixture from conftest.py (3 test tickers).
Originally part of tests/data_sources/cvm/test_bridge.py; split as part of
test-reorg.
"""
from __future__ import annotations


class TestBridgeQuery:
    """Test bridge query_engine."""

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
