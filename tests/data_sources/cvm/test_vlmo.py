"""Tests for data_sources/cvm/vlmo/ — VLMO insider trading data source.

Uses synthetic SQLite DBs — no network, no real CVM data.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm.vlmo.catalog import SCHEMA_SQL


@pytest.fixture
def vlmo_db(tmp_path, monkeypatch):
    """Create a synthetic VLMO database with test data."""
    db = tmp_path / "vlmo.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA_SQL)

    # Insert test movements
    conn.executemany(
        """INSERT INTO vlmo_movements
           (CNPJ_Companhia, Data_Movimentacao, Tipo_Cargo, Empresa,
            Tipo_Movimentacao, Tipo_Ativo, Quantidade, Preco_Unitario,
            Volume, Descricao_Movimentacao, Data_Referencia, Nome_Companhia)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("33000167000101", "2026-07-15", "Diretor", "João Silva",
             "Compra", "Ação", 10000, 38.50, 385000,
             "Compra de ações ordinárias", "2026-07-16", "PETROBRAS"),
            ("33000167000101", "2026-07-10", "Diretor", "Maria Santos",
             "Venda", "Ação", 5000, 37.80, 189000,
             "Venda de ações preferenciais", "2026-07-11", "PETROBRAS"),
            ("33000167000101", "2026-06-20", "Oficial", "Carlos Lima",
             "Compra", "Ação", 20000, 36.00, 720000,
             "Compra de ações", "2026-06-21", "PETROBRAS"),
        ]
    )
    conn.execute("INSERT INTO sync_state VALUES ('2026-07-25T10:00:00', 2026, 3)")
    conn.commit()
    conn.close()

    # Patch db_path
    monkeypatch.setattr("data_sources.cvm.vlmo.catalog.db_path", lambda: db)
    return db


class TestQueryEngine:
    def test_query_history(self, vlmo_db):
        from data_sources.cvm.vlmo.query_engine import query
        # Use CNPJ directly (no bridge needed)
        r = query(company="33000167000101", limit=10)
        assert r["status"] == "ok"
        assert r["count"] == 3
        assert len(r["movements"]) == 3
        # Newest first
        assert r["movements"][0]["Data_Movimentacao"] == "2026-07-15"

    def test_query_by_role(self, vlmo_db):
        from data_sources.cvm.vlmo.query_engine import query
        r = query(company="33000167000101", by_role=True)
        assert r["status"] == "ok"
        roles = r["by_role"]
        assert len(roles) == 2  # Diretor + Oficial
        # Diretor: 1 buy (10000) + 1 sell (5000)
        diretor = next(r for r in roles if r["Tipo_Cargo"] == "Diretor")
        assert diretor["total_bought"] == 10000
        assert diretor["total_sold"] == 5000

    def test_query_summary(self, vlmo_db):
        from data_sources.cvm.vlmo.query_engine import query
        r = query(company="33000167000101", summary=True)
        assert r["status"] == "ok"
        assert len(r["monthly"]) == 2  # July 2026 + June 2026
        july = next(m for m in r["monthly"] if m["month"] == "2026-07")
        assert july["bought"] == 10000
        assert july["sold"] == 5000
        assert july["net_shares"] == 5000  # 10000 - 5000

    def test_query_not_found(self, vlmo_db):
        from data_sources.cvm.vlmo.query_engine import query
        r = query(company="99999999000199", limit=10)
        assert r["status"] == "not_found"

    def test_query_requires_company(self, vlmo_db):
        from data_sources.cvm.vlmo.query_engine import query
        r = query()
        assert r["status"] == "error"


class TestStatusReporter:
    def test_status_ok(self, vlmo_db):
        from data_sources.cvm.vlmo.status_reporter import status
        r = status()
        assert r["status"] == "ok"
        assert r["movement_count"] == 3
        assert r["company_count"] == 1
        assert r["buy_transactions"] == 2
        assert r["sell_transactions"] == 1

    def test_status_not_synced(self, tmp_path, monkeypatch):
        monkeypatch.setattr("data_sources.cvm.vlmo.catalog.db_path",
                            lambda: tmp_path / "nonexistent.db")
        from data_sources.cvm.vlmo.status_reporter import status
        r = status()
        assert r["status"] == "not_synced"
