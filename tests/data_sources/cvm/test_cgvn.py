"""Tests for data_sources/cvm/cgvn/ — CGVN governance data source.

Uses synthetic SQLite DBs — no network, no real CVM data.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm.cgvn.catalog import SCHEMA_SQL


@pytest.fixture
def cgvn_db(tmp_path, monkeypatch):
    """Create a synthetic CGVN database with test data."""
    db = tmp_path / "cgvn.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA_SQL)

    conn.executemany(
        """INSERT INTO cgvn_practices
           (CNPJ_Companhia, Data_Referencia, ID_Item, Pratica_Recomendada,
            Pratica_Adotada, Capitulo, Principio, Explicacao, Nome_Empresarial)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("33000167000101", "2025-06-30", "1.1", "Possuir diretoria independente",
             "Sim", "Conselho de Administração", "Independência", "Sim, possui", "PETROBRAS"),
            ("33000167000101", "2025-06-30", "1.2", "Comitê de auditoria",
             "Parcialmente", "Conselho de Administração", "Independência", "Parcial", "PETROBRAS"),
            ("33000167000101", "2025-06-30", "2.1", "Divulgar transações relacionadas",
             "Sim", "Transações Relacionadas", "Transparência", "Sim", "PETROBRAS"),
            ("33000167000101", "2025-06-30", "2.2", "Política de dividendos",
             "Não", "Transações Relacionadas", "Transparência", "Não possui", "PETROBRAS"),
        ]
    )
    conn.execute("INSERT INTO sync_state VALUES ('2026-07-25T10:00:00', 2025, 4)")
    conn.commit()
    conn.close()

    monkeypatch.setattr("data_sources.cvm._db.cgvn_db_path", lambda: db)
    return db


class TestQueryEngine:
    def test_query_practices(self, cgvn_db):
        from data_sources.cvm.cgvn.query_engine import query
        r = query(company="33000167000101")
        assert r["status"] == "ok"
        assert r["count"] == 4
        assert len(r["practices"]) == 4

    def test_query_score(self, cgvn_db):
        from data_sources.cvm.cgvn.query_engine import query
        r = query(company="33000167000101", score=True)
        assert r["status"] == "ok"
        assert r["total_practices"] == 4
        assert r["adopted_sim"] == 2
        assert r["adopted_nao"] == 1
        assert r["adopted_parcialmente"] == 1
        assert r["score_pct"] == 0.5  # 2/4

    def test_query_by_chapter(self, cgvn_db):
        from data_sources.cvm.cgvn.query_engine import query
        r = query(company="33000167000101", by_chapter=True)
        assert r["status"] == "ok"
        chapters = r["by_chapter"]
        assert len(chapters) == 2  # Conselho + Transações
        conselho = next(c for c in chapters if c["Capitulo"] == "Conselho de Administração")
        assert conselho["total"] == 2
        assert conselho["adopted"] == 1
        assert conselho["partial"] == 1

    def test_query_not_found(self, cgvn_db):
        from data_sources.cvm.cgvn.query_engine import query
        r = query(company="99999999000199")
        assert r["status"] == "not_found"

    def test_query_requires_company(self, cgvn_db):
        from data_sources.cvm.cgvn.query_engine import query
        r = query()
        assert r["status"] == "error"


class TestStatusReporter:
    def test_status_ok(self, cgvn_db):
        from data_sources.cvm.cgvn.status_reporter import status
        r = status()
        assert r["status"] == "ok"
        assert r["practice_count"] == 4
        assert r["company_count"] == 1
