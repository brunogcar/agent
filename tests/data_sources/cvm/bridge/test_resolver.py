"""tests/data_sources/cvm/bridge/test_resolver.py -- _bridge.py resolver tests.

Tests cover:
  - _bridge.py resolve_company: ticker -> (cnpj, cd_cvm) -> empresas, with
    cd_cvm fallback + auto-sync-on-demand + formatted-CNPJ matching

Uses the `dfp_with_bridge` fixture from conftest.py for the base setup.
Some tests build their own synthetic DBs (when they need a different shape).

Originally part of tests/data_sources/cvm/test_bridge.py; split as part of
test-reorg.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from data_sources.cvm.bridge.catalog import SCHEMA_SQL


# ════════════════════════════════════════════════════════════════════════════
# RESOLVER (_bridge.py) TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeResolver:
    """Test _bridge.py resolve_company with the new ticker_map table."""

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
        """bridge.db doesn't exist AND FCA doesn't exist -> _resolve_via_bridge returns (None, None).

        [v1.3] FCA is the primary resolver now. If FCA exists, it resolves
        even without bridge.db. This test mocks BOTH to be nonexistent.
        """
        nonexistent = tmp_path / "nonexistent.db"
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                            lambda: nonexistent)
        # [v1.3] Also mock FCA as nonexistent so _resolve_via_fca returns None
        monkeypatch.setattr("data_sources.cvm._db.fca_db_path",
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
