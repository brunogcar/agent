"""Tests for data_sources/cvm/fca/ — FCA registration data source.

Uses synthetic SQLite DBs — no network, no real CVM data.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm.fca.catalog import SCHEMA_SQL


@pytest.fixture
def fca_db(tmp_path, monkeypatch):
    """Create a synthetic FCA database with test data."""
    db = tmp_path / "fca.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA_SQL)

    # Insert test geral data
    conn.executemany(
        """INSERT INTO fca_geral
           (CNPJ_Companhia, Codigo_CVM, Data_Referencia, Nome_Empresarial,
            Setor_Atividade, Especie_Controle_Acionario, Situacao_Emissor,
            Pagina_Web, Dia_Encerramento_Exercicio_Social,
            Mes_Encerramento_Exercicio_Social)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("33000167000101", "9512", "2025-06-30", "PETROBRAS",
             "Petróleo, Gás e Biocombustíveis", "PETROBRAS", "ATIVO",
             "www.petrobras.com.br", 31, 12),
        ]
    )

    # Insert test valor_mobiliario data
    conn.executemany(
        """INSERT INTO fca_valor_mobiliario
           (CNPJ_Companhia, Codigo_Negociacao, Segmento, Mercado,
            Valor_Mobiliario, Classe_Acao_Preferencial, Data_Inicio_Listagem,
            Data_Referencia)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("33000167000101", "PETR4", "Novo Mercado", "BOVESPA",
             "AÇÃO PN", "PN", "2000-01-20", "2025-06-30"),
            ("33000167000101", "PETR3", "Novo Mercado", "BOVESPA",
             "AÇÃO ON", "", "2000-01-20", "2025-06-30"),
        ]
    )

    # Insert test pais_estrangeiro data
    conn.executemany(
        """INSERT INTO fca_pais_estrangeiro
           (CNPJ_Companhia, Pais, Data_Admissao_Negociacao, Data_Referencia)
           VALUES (?, ?, ?, ?)""",
        [
            ("33000167000101", "ESTADOS UNIDOS", "2000-07-26", "2025-06-30"),
        ]
    )

    conn.execute("INSERT INTO sync_state VALUES ('2026-07-25T10:00:00', 2025, 4)")
    conn.commit()
    conn.close()

    monkeypatch.setattr("data_sources.cvm.fca.catalog.db_path", lambda: db)
    return db


class TestQueryEngine:
    def test_query_ticker(self, fca_db):
        from data_sources.cvm.fca.query_engine import query
        r = query(ticker="PETR4")
        assert r["status"] == "ok"
        assert r["ticker"] == "PETR4"
        assert r["cnpj"] == "33000167000101"
        assert r["cd_cvm"] == "9512"
        assert r["segmento"] == "Novo Mercado"
        assert r["nome_empresarial"] == "PETROBRAS"

    def test_query_ticker_not_found(self, fca_db):
        from data_sources.cvm.fca.query_engine import query
        r = query(ticker="UNKNOWN4")
        assert r["status"] == "not_found"

    def test_query_company(self, fca_db):
        from data_sources.cvm.fca.query_engine import query
        r = query(company="PETR4")
        assert r["status"] == "ok"
        assert r["cnpj"] == "33000167000101"
        assert r["security_count"] == 2  # PETR3 + PETR4

    def test_query_foreign_listings(self, fca_db):
        from data_sources.cvm.fca.query_engine import query
        r = query(company="PETR4", foreign_listings=True)
        assert r["status"] == "ok"
        assert r["count"] == 1
        assert r["foreign_listings"][0]["Pais"] == "ESTADOS UNIDOS"

    def test_query_requires_input(self, fca_db):
        from data_sources.cvm.fca.query_engine import query
        r = query()
        assert r["status"] == "error"


class TestStatusReporter:
    def test_status_ok(self, fca_db):
        from data_sources.cvm.fca.status_reporter import status
        r = status()
        assert r["status"] == "ok"
        assert r["geral_count"] == 1
        assert r["valor_mobiliario_count"] == 2
        assert r["pais_estrangeiro_count"] == 1
        assert r["ticker_count"] == 2
        assert r["company_count"] == 1
