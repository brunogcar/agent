"""tests/data_sources/cvm/test_ipe_query.py -- Tests for IPE query engine.

Uses a synthetic SQLite DB (in tmp_path). Never touches the real ipe.db.
"""

from __future__ import annotations

import sqlite3
import pytest

from data_sources.cvm.ipe.catalog import SCHEMA_SQL


@pytest.fixture
def ipe_db(tmp_path, monkeypatch):
    """Create a synthetic IPE database with test data."""
    db_path = tmp_path / "ipe.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    # Insert test events
    events = [
        ("33000167000101", "009512", "PETROLEO BRASILEIRO S.A. PETROBRAS",
         "2024-03-15", "2024-03-14", "Comunicado ao Mercado", "Aviso aos Acionistas",
         "Ordinaria", "Dividendo aprovado pela AGE", "PDF", 1, "PROT001", "http://example.com/1", 2024),
        ("33000167000101", "009512", "PETROLEO BRASILEIRO S.A. PETROBRAS",
         "2024-05-10", "2024-05-09", "Comunicado ao Mercado", "Aviso aos Acionistas",
         "Ordinaria", "Resultado 1T 2024", "PDF", 1, "PROT002", "http://example.com/2", 2024),
        ("33000167000101", "009512", "PETROLEO BRASILEIRO S.A. PETROBRAS",
         "2024-08-08", "2024-08-07", "Comunicado ao Mercado", "Fato Relevante",
         "Ordinaria", "Aquisicao de ativos", "PDF", 1, "PROT003", "http://example.com/3", 2024),
    ]

    for e in events:
        conn.execute(
            """INSERT INTO eventos (cnpj, cd_cvm, nome, data_entrega, data_referencia,
               categoria, tipo, especie, assunto, tipo_apresentacao, versao,
               protocolo, link_download, ano_origem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            e,
        )

    conn.commit()
    conn.close()

    def mock_connect_ipe(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.cvm._db.connect_ipe", mock_connect_ipe)
    monkeypatch.setattr("data_sources.cvm.ipe.query_engine.connect_ipe", mock_connect_ipe)
    monkeypatch.setattr("data_sources.cvm.ipe.status_reporter.connect_ipe", mock_connect_ipe)
    monkeypatch.setattr("data_sources.cvm.ipe.status_reporter.ipe_db_path", lambda: db_path)
    return db_path


class TestIPEQuery:
    def test_query_by_name(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(company="PETROBRAS")
        assert result["status"] == "ok"
        assert result["count"] == 3

    def test_query_by_cnpj(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(company="33000167000101")
        assert result["status"] == "ok"
        assert result["count"] == 3

    def test_query_filter_keyword(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(keyword="dividendo")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert "Dividendo" in result["events"][0]["assunto"]

    def test_query_filter_categoria(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(categoria="Comunicado")
        assert result["status"] == "ok"
        assert result["count"] == 3

    def test_query_filter_tipo(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(tipo="Fato Relevante")
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_query_filter_date_range(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(data_from="2024-05-01", data_to="2024-06-30")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["events"][0]["assunto"] == "Resultado 1T 2024"

    def test_query_not_found(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(company="NONEXISTENT")
        assert result["status"] == "not_found"
        assert result["count"] == 0

    def test_query_limit(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(company="PETROBRAS", limit=2)
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_query_sorted_by_date_desc(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import query
        result = query(company="PETROBRAS")
        dates = [e["data_entrega"] for e in result["events"]]
        assert dates == sorted(dates, reverse=True)


class TestIPESearch:
    def test_search(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import search
        result = search(query="PETROBRAS")
        assert result["status"] == "ok"
        assert len(result["companies"]) >= 1
        assert result["companies"][0]["num_events"] == 3

    def test_search_not_found(self, ipe_db):
        from data_sources.cvm.ipe.query_engine import search
        result = search(query="NONEXISTENT")
        assert result["status"] == "not_found"


class TestIPEStatus:
    def test_status(self, ipe_db):
        from data_sources.cvm.ipe.status_reporter import status
        result = status()
        assert result["status"] == "ok"
        assert result["form"] == "IPE"
        assert result["eventos"] == 3
        assert result["year_range"]["min"] == 2024
        assert result["year_range"]["max"] == 2024
