"""tests/data_sources/cvm/test_dfp_query.py -- Tests for DFP query engine.

Uses a synthetic SQLite DB (in-memory or temp file) to test query logic
without needing real CVM data.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from data_sources.cvm._db import _ensure_schema


@pytest.fixture
def dfp_db(tmp_path, monkeypatch):
    """Create a synthetic DFP database with test data."""
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)

    # Insert a test company (JHSF-style)
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'JHSF PARTICIPACOES S.A.', 2023, '000123')"
    )
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (2, '33000167000101', 'JHSF PARTICIPACOES S.A.', 2024, '000123')"
    )

    # Insert some contas (annual flow + snapshot)
    # BPA snapshot (data_ini='')
    conn.execute(
        """INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado,
           data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor)
           VALUES (1, '1', 'Ativo Total', 'BPA', 1, '', '2023-12-31', 12, 'ÚLTIMO', 1, 11078069)"""
    )
    conn.execute(
        """INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado,
           data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor)
           VALUES (2, '1', 'Ativo Total', 'BPA', 1, '', '2024-12-31', 12, 'ÚLTIMO', 1, 13293747)"""
    )
    # DRE flow (data_ini='2023-01-01')
    conn.execute(
        """INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado,
           data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor)
           VALUES (1, '3.01', 'Receita Líquida', 'DRE', 1, '2023-01-01', '2023-12-31', 12, 'ÚLTIMO', 1, 1593474)"""
    )
    conn.execute(
        """INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado,
           data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor)
           VALUES (2, '3.01', 'Receita Líquida', 'DRE', 1, '2024-01-01', '2024-12-31', 12, 'ÚLTIMO', 1, 1607933)"""
    )
    conn.commit()
    conn.close()

    # Patch connect_dfp to use this DB
    def mock_connect_dfp(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
    monkeypatch.setattr("data_sources.cvm.dfp.query_engine.connect_dfp", mock_connect_dfp)
    monkeypatch.setattr("data_sources.cvm.dfp.status_reporter.connect_dfp", mock_connect_dfp)
    monkeypatch.setattr("data_sources.cvm.dfp.status_reporter.dfp_db_path", lambda: db_path)
    # [v1.0.2] Prevent _bridge.py from trying to open the real cad.db during tests.
    # Without this, _resolve_via_cad() finds the real JHSF in cad.db and returns
    # JHSF's real CNPJ — which doesn't match the synthetic test data (which uses
    # Petrobras's CNPJ for a company named JHSF).
    from pathlib import Path as _P
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path", lambda: _P("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad", lambda name: (None, None))
    return db_path


class TestDFPQuery:
    """Test DFP query engine."""

    def test_query_by_name(self, dfp_db):
        """Query by company name fragment."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="JHSF")
        assert result["status"] == "ok"
        assert "JHSF" in result["company"]
        assert "2024" in result["periods"]
        assert "2023" in result["periods"]

    def test_query_by_cnpj(self, dfp_db):
        """Query by CNPJ."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="33000167000101")
        assert result["status"] == "ok"
        assert "JHSF" in result["company"]

    def test_query_filter_grupo(self, dfp_db):
        """Query filtered by grupo (BPA only)."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="JHSF", grupo="BPA")
        assert result["status"] == "ok"
        # Only BPA groups should be present
        for year_data in result["periods"].values():
            for grp in year_data:
                assert "BPA" in grp

    def test_query_filter_codigo(self, dfp_db):
        """Query filtered by codigo prefix."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="JHSF", codigo="1")
        assert result["status"] == "ok"

    def test_query_not_found(self, dfp_db):
        """Query for non-existent company."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_query_no_company(self, dfp_db):
        """Query without company parameter."""
        from data_sources.cvm.dfp.query_engine import query
        result = query()
        assert result["status"] == "error"

    def test_resumo(self, dfp_db):
        """Test resumo (summary) query."""
        from data_sources.cvm.dfp.query_engine import resumo
        result = resumo(company="JHSF")
        assert result["status"] == "ok"
        assert "Ativo Total" in result["metrics"]
        assert "Receita Líquida" in result["metrics"]

    def test_search(self, dfp_db):
        """Test company search."""
        from data_sources.cvm.dfp.query_engine import search
        result = search(query="JHSF")
        assert result["status"] == "ok"
        assert len(result["companies"]) >= 1
        assert "JHSF" in result["companies"][0]["nome"]

    def test_status(self, dfp_db):
        """Test status report."""
        from data_sources.cvm.dfp.status_reporter import status
        result = status()
        assert result["status"] == "ok"
        assert result["form"] == "DFP"
        assert result["empresas"] == 2
        assert result["contas"] == 4

    def test_data_ini_exerc_stored(self, dfp_db):
        """Verify data_ini_exerc is stored correctly (snapshot="" vs flow=non-empty)."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="JHSF", grupo="BPA")
        # BPA is a snapshot → data_ini_exerc should be ""
        for year_data in result["periods"].values():
            for grp, entries in year_data.items():
                for entry in entries:
                    assert entry["data_ini_exerc"] == ""  # BPA snapshot

    def test_flow_vs_snapshot_distinguished(self, dfp_db):
        """Verify flows have data_ini_exerc != "" and snapshots have == ""."""
        from data_sources.cvm.dfp.query_engine import query
        result = query(company="JHSF")
        for year, year_data in result["periods"].items():
            for grp, entries in year_data.items():
                for entry in entries:
                    if "BPA" in grp or "BPP" in grp:
                        assert entry["data_ini_exerc"] == ""  # snapshot
                    elif "DRE" in grp:
                        assert entry["data_ini_exerc"] != ""  # flow
