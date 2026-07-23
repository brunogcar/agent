"""tests/data_sources/cvm/test_cad_query.py -- Tests for CAD query engine.

Uses a synthetic SQLite DB (in tmp_path). Never touches the real cad.db.
"""

from __future__ import annotations

import sqlite3
import pytest

from data_sources.cvm.cad.catalog import SCHEMA_SQL, ALL_COLS


@pytest.fixture
def cad_db(tmp_path, monkeypatch):
    """Create a synthetic CAD database with test data."""
    db_path = tmp_path / "cad.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    # Insert 3 test companies
    companies = [
        # PETROBRAS (active, state-owned, oil)
        ("33.000.167/0001-01", "PETROLEO BRASILEIRO S.A. PETROBRAS", "PETROBRAS",
         "1961-07-26", "1953-10-03", "", "", "ATIVO", "2020-04-30", "009512",
         "Petróleo", "Bolsa", "Categoria A", "2020-04-30",
         "EM FUNCIONAMENTO NORMAL", "2020-04-30", "ESTATAL",
         "", "", "", "", "RIO DE JANEIRO", "RJ", "BRASIL", "20000",
         "21", "22220000", "", "", "ri@petrobras.com.br",
         "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "",
         "33.851.205/0001-79", "PricewaterhouseCoopers"),
        # VALE (active, private, mining)
        ("33.592.510/0001-54", "VALE S.A.", "VALE",
         "2002-06-12", "1942-06-01", "", "", "ATIVO", "2020-04-30", "024311",
         "Mineração", "Bolsa", "Categoria A", "2020-04-30",
         "EM FUNCIONAMENTO NORMAL", "2020-04-30", "PRIVADO",
         "", "", "", "", "RIO DE JANEIRO", "RJ", "BRASIL", "20000",
         "21", "37820000", "", "", "ri@vale.com",
         "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "",
         "", "Deloitte"),
        # Cancelled company
        ("00.000.000/0001-00", "EMPRESA CANCELADA LTDA", "CANCELADA SA",
         "2010-01-01", "2009-01-01", "2024-01-15", "Inatividade", "CANCELADA",
         "2024-01-15", "000001",
         "Comércio", "Bolsa", "Categoria B", "2010-01-01",
         "CANCELADA", "2024-01-15", "PRIVADO",
         "", "", "", "", "SAO PAULO", "SP", "BRASIL", "01000",
         "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", ""),
    ]

    placeholders = ", ".join("?" * len(ALL_COLS))
    for c in companies:
        # Pad to 46 columns if needed
        padded = list(c) + [""] * (len(ALL_COLS) - len(c))
        conn.execute(f"INSERT INTO cia_aberta VALUES ({placeholders})", padded[:len(ALL_COLS)])

    conn.execute(
        "INSERT INTO sync_state (synced_at, rows, size_kb) VALUES (?, ?, ?)",
        ("2026-07-23T12:00:00", 3, 1.5),
    )
    conn.commit()
    conn.close()

    def mock_connect_cad(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("data_sources.cvm._db.connect_cad", mock_connect_cad)
    monkeypatch.setattr("data_sources.cvm.cad.query_engine.connect_cad", mock_connect_cad)
    monkeypatch.setattr("data_sources.cvm.cad.status_reporter.connect_cad", mock_connect_cad)
    monkeypatch.setattr("data_sources.cvm.cad.status_reporter.cad_db_path", lambda: db_path)
    return db_path


class TestCADLookup:
    def test_lookup_by_cnpj(self, cad_db):
        from data_sources.cvm.cad.query_engine import lookup
        result = lookup(cnpj="33000167000101")
        assert result["status"] == "ok"
        assert "PETROBRAS" in result["company"]["DENOM_SOCIAL"]

    def test_lookup_by_formatted_cnpj(self, cad_db):
        from data_sources.cvm.cad.query_engine import lookup
        result = lookup(cnpj="33.000.167/0001-01")
        assert result["status"] == "ok"
        assert "PETROBRAS" in result["company"]["DENOM_SOCIAL"]

    def test_lookup_by_cd_cvm(self, cad_db):
        from data_sources.cvm.cad.query_engine import lookup
        result = lookup(cd_cvm="009512")
        assert result["status"] == "ok"
        assert "PETROBRAS" in result["company"]["DENOM_SOCIAL"]

    def test_lookup_by_name(self, cad_db):
        from data_sources.cvm.cad.query_engine import lookup
        result = lookup(name="VALE")
        assert result["status"] == "ok"
        assert "VALE" in result["company"]["DENOM_SOCIAL"]

    def test_lookup_not_found(self, cad_db):
        from data_sources.cvm.cad.query_engine import lookup
        result = lookup(name="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_lookup_full_columns(self, cad_db):
        from data_sources.cvm.cad.query_engine import lookup
        result = lookup(cd_cvm="009512", full=True)
        assert result["status"] == "ok"
        assert "AUDITOR" in result["company"]
        assert "PricewaterhouseCoopers" in result["company"]["AUDITOR"]


class TestCADSearch:
    def test_search_all_active(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        result = search()
        assert result["status"] == "ok"
        assert result["total_matches"] == 2  # 2 active companies

    def test_search_by_setor(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        # Use partial match without accent (SQLite UPPER doesn't handle non-ASCII)
        result = search(setor="Petr")
        assert result["status"] == "ok"
        assert result["total_matches"] == 1
        assert "PETROBRAS" in result["companies"][0]["DENOM_SOCIAL"]

    def test_search_by_setor_mining(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        result = search(setor="Minera")
        assert result["status"] == "ok"
        assert result["total_matches"] == 1
        assert "VALE" in result["companies"][0]["DENOM_SOCIAL"]

    def test_search_by_controle(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        result = search(controle="ESTATAL")
        assert result["status"] == "ok"
        assert result["total_matches"] == 1
        assert "PETROBRAS" in result["companies"][0]["DENOM_SOCIAL"]

    def test_search_by_uf(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        result = search(uf="RJ")
        assert result["status"] == "ok"
        assert result["total_matches"] == 2  # PETROBRAS + VALE

    def test_search_include_cancelled(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        result = search(active_only=False)
        assert result["status"] == "ok"
        assert result["total_matches"] == 3  # all 3 companies

    def test_search_by_sit_cancelled(self, cad_db):
        from data_sources.cvm.cad.query_engine import search
        result = search(sit="CANCELADA", active_only=False)
        assert result["status"] == "ok"
        assert result["total_matches"] == 1
        assert "CANCELADA" in result["companies"][0]["DENOM_SOCIAL"]


class TestCADSectors:
    def test_sectors(self, cad_db):
        from data_sources.cvm.cad.query_engine import sectors
        result = sectors()
        assert result["status"] == "ok"
        assert "Petróleo" in {s["setor"] for s in result["sectors"]}
        assert "Mineração" in {s["setor"] for s in result["sectors"]}


class TestCADStatus:
    def test_status(self, cad_db):
        from data_sources.cvm.cad.status_reporter import status
        result = status()
        assert result["status"] == "ok"
        assert result["form"] == "CAD"
        assert result["total_companies"] == 3
        assert result["active"] == 2
        assert result["cancelled"] == 1
