"""tests/data_sources/cvm/bridge/conftest.py -- Shared fixtures for bridge tests.

Fixtures extracted from the original test_bridge.py. Helper functions (the
mock factories and _patch_* helpers) live in _helpers.py and are imported
explicitly by each test module as needed.

Inherits the autouse env-var fixture from the parent
tests/data_sources/cvm/conftest.py.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from data_sources.cvm.bridge.catalog import SCHEMA_SQL

from tests.data_sources.cvm.bridge._helpers import _insert_bridge_row


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


@pytest.fixture
def populated_bridge(bridge_db):
    """Bridge.db with 3 test tickers.

    Originally defined inside TestBridgeQuery; moved here so it can be shared
    by any bridge test that needs a populated ticker_map.
    """
    _insert_bridge_row(bridge_db, "PETR4", "PETR", "9512", "PETROBRAS",
                       "33000167000101", "PETROLEO BRASILEIRO S.A.",
                       "PETROBRAS", "ATIVO", "Petróleo", "Bolsa", "2024-01-01")
    _insert_bridge_row(bridge_db, "VALE3", "VALE", "4170", "VALE",
                       "33592510000154", "VALE S.A.", "VALE",
                       "ATIVO", "Mineração", "Bolsa", "2024-01-01")
    _insert_bridge_row(bridge_db, "UNKW4", "UNKW", "99999", "UNKNOWN",
                       "", "UNKNOWN", "UNKNOWN", "", "", "", "2024-01-01")
    return bridge_db


@pytest.fixture
def dfp_with_bridge(tmp_path, monkeypatch):
    """Create a synthetic DFP db + bridge.db, patch all paths.

    Originally defined inside TestBridgeResolver; moved here so it can be
    shared by any bridge test that needs a populated DFP+bridge setup.
    """
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
