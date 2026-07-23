"""tests/data_sources/cvm/test_itr_query.py -- Tests for ITR query engine.

Uses a synthetic SQLite DB (in tmp_path) to test query logic without
needing real CVM data. Never touches the real itr.db.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from data_sources.cvm._db import _ensure_schema


@pytest.fixture
def itr_db(tmp_path, monkeypatch):
    """Create a synthetic ITR database with test data (quarterly cumulative)."""
    db_path = tmp_path / "itr.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)

    # Insert a test company for 2 years
    for ano, emp_id in [(2023, 1), (2024, 2)]:
        conn.execute(
            "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (?, '33000167000101', 'JHSF PARTICIPACOES S.A.', ?, '000123')",
            (emp_id, ano),
        )

    # Insert quarterly ITR data (cumulative: Q1=3, H1=6, 9M=9)
    # DRE flow (Receita Líquida, code 3.01) for 2024
    for meses, dt_fim, valor in [
        (3, "2024-03-31", 293596),    # Q1
        (6, "2024-06-30", 689957),    # H1
        (9, "2024-09-30", 1063587),   # 9M
    ]:
        conn.execute(
            f"""INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado,
               data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor)
               VALUES (2, '3.01', 'Receita Líquida', 'DRE', 1,
               '2024-01-01', '{dt_fim}', {meses}, 'ÚLTIMO', 1, {valor})"""
        )

    # BPA snapshot (Ativo Total, code 1) for 2024 quarters
    for meses, dt_fim, valor in [
        (3, "2024-03-31", 11975291),
        (6, "2024-06-30", 11970125),
        (9, "2024-09-30", 12445119),
    ]:
        conn.execute(
            f"""INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado,
               data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor)
               VALUES (2, '1', 'Ativo Total', 'BPA', 1,
               '', '{dt_fim}', {meses}, 'ÚLTIMO', 1, {valor})"""
        )

    conn.commit()
    conn.close()

    def mock_connect_itr(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.cvm._db.connect_itr", mock_connect_itr)
    monkeypatch.setattr("data_sources.cvm.itr.query_engine.connect_itr", mock_connect_itr)
    monkeypatch.setattr("data_sources.cvm.itr.status_reporter.connect_itr", mock_connect_itr)
    monkeypatch.setattr("data_sources.cvm.itr.status_reporter.itr_db_path", lambda: db_path)
    return db_path


class TestITRQuery:
    """Test ITR query engine."""

    def test_query_by_name(self, itr_db):
        """Query by company name fragment."""
        from data_sources.cvm.itr.query_engine import query
        result = query(company="JHSF")
        assert result["status"] == "ok"
        assert "JHSF" in result["company"]
        assert result["form"] == "ITR"
        # Should have quarterly periods
        assert "2024-03-31" in result["periods"]
        assert "2024-06-30" in result["periods"]
        assert "2024-09-30" in result["periods"]

    def test_query_returns_cumulative_note(self, itr_db):
        """ITR query should note that values are CUMULATIVE, not standalone."""
        from data_sources.cvm.itr.query_engine import query
        result = query(company="JHSF")
        assert "note" in result
        assert "CUMULATIVE" in result["note"]

    def test_query_filter_grupo(self, itr_db):
        """Query filtered by grupo (DRE only)."""
        from data_sources.cvm.itr.query_engine import query
        result = query(company="JHSF", grupo="DRE")
        assert result["status"] == "ok"
        for period_data in result["periods"].values():
            for grp in period_data:
                if grp in ("ano", "meses", "period_label"):
                    continue
                assert "DRE" in grp

    def test_query_not_found(self, itr_db):
        """Query for non-existent company."""
        from data_sources.cvm.itr.query_engine import query
        result = query(company="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_query_no_company(self, itr_db):
        """Query without company parameter."""
        from data_sources.cvm.itr.query_engine import query
        result = query()
        assert result["status"] == "error"

    def test_resumo(self, itr_db):
        """Test resumo (summary) query — should return cumulative values."""
        from data_sources.cvm.itr.query_engine import resumo
        result = resumo(company="JHSF")
        assert result["status"] == "ok"
        assert "Ativo Total" in result["metrics"]
        assert "Receita Líquida" in result["metrics"]

    def test_resumo_values_are_cumulative(self, itr_db):
        """Verify ITR resumo returns cumulative values (not standalone)."""
        from data_sources.cvm.itr.query_engine import resumo
        result = resumo(company="JHSF")
        receita = result["metrics"]["Receita Líquida"]
        # Q1 should be 293596, H1 should be 689957 (cumulative, not standalone)
        assert receita["2024-03-31"] == 293596   # Q1 cumulative
        assert receita["2024-06-30"] == 689957   # H1 cumulative (not 689957-293596)
        assert receita["2024-09-30"] == 1063587  # 9M cumulative

    def test_search(self, itr_db):
        """Test company search in ITR database."""
        from data_sources.cvm.itr.query_engine import search
        result = search(query="JHSF")
        assert result["status"] == "ok"
        assert len(result["companies"]) >= 1
        assert "JHSF" in result["companies"][0]["nome"]

    def test_status(self, itr_db):
        """Test ITR status report."""
        from data_sources.cvm.itr.status_reporter import status
        result = status()
        assert result["status"] == "ok"
        assert result["form"] == "ITR"
        assert result["empresas"] == 2
        assert result["contas"] == 6

    def test_bpa_snapshot_has_empty_data_ini(self, itr_db):
        """BPA snapshots should have data_ini_exerc="" (not a flow period)."""
        from data_sources.cvm.itr.query_engine import query
        result = query(company="JHSF", grupo="BPA")
        for period, period_data in result["periods"].items():
            for key in period_data:
                if key in ("ano", "meses", "period_label"):
                    continue
                for entry in period_data[key]:
                    assert entry["data_ini_exerc"] == ""  # BPA snapshot

    def test_dre_flow_has_data_ini(self, itr_db):
        """DRE flows should have data_ini_exerc != "" (period flow)."""
        from data_sources.cvm.itr.query_engine import query
        result = query(company="JHSF", grupo="DRE")
        for period, period_data in result["periods"].items():
            for key in period_data:
                if key in ("ano", "meses", "period_label"):
                    continue
                for entry in period_data[key]:
                    assert entry["data_ini_exerc"] != ""  # DRE flow
