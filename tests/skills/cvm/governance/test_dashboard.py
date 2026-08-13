"""Tests for governance dashboard mode.

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive; we call it exactly once per file.
"""
from __future__ import annotations
import pytest
from skills.cvm.governance.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self):
        r = dashboard()
        assert r["status"] == "error"

    def test_dashboard_tab_structure(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert r["status"] == "ok"
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Practices", "By Chapter"]


# ── Helpers ──────────────────────────────────────────────────────────────────
import sqlite3
from pathlib import Path

def _make_cgvn_db(tmp_path):
    db_path = tmp_path / "cgvn.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE contas (codigo TEXT, descricao TEXT, grupo TEXT,
        data_fim_exerc TEXT, valor TEXT, meses INTEGER, consolidado INTEGER,
        id_empresa INTEGER)""")
    conn.execute("""CREATE TABLE empresas (id INTEGER PRIMARY KEY, cd_cvm TEXT, nome TEXT)""")
    conn.execute("INSERT INTO empresas VALUES (1, '9512', 'PETROBRAS')")
    conn.execute("""INSERT INTO contas VALUES ('1', 'Pratica', 'CGVN',
        '2023-12-31', 'Sim', 12, 1, 1)""")
    # [v1.2] cgvn_practices table — what the CGVN query_engine actually
    # queries. Populate 3 rows with distinct Pratica_Adotada values so the
    # practices doughnut chart has 3 segments (Adequado / Parcialmente / Não
    # Adequado). CNPJ_Companhia is stored normalized (digits-only) to match
    # the production sync_engine format.
    conn.execute("""CREATE TABLE cgvn_practices (
        CNPJ_Companhia TEXT, Data_Referencia TEXT, ID_Documento INTEGER,
        Nome_Empresarial TEXT, Versao INTEGER, ID_Item TEXT,
        Pratica_Recomendada TEXT, Pratica_Adotada TEXT, Capitulo TEXT,
        Principio TEXT, Explicacao TEXT)""")
    conn.executemany(
        "INSERT INTO cgvn_practices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("33000167000101", "2023-12-31", 1, "PETROBRAS", 1, "3.1",
             "Practice A", "Sim", "Cap 1", "P1", "Adopted"),
            ("33000167000101", "2023-12-31", 1, "PETROBRAS", 1, "3.2",
             "Practice B", "Parcialmente", "Cap 1", "P2", "Partial"),
            ("33000167000101", "2023-12-31", 1, "PETROBRAS", 1, "3.3",
             "Practice C", "Não", "Cap 2", "P3", "Not adopted"),
        ],
    )
    conn.commit()
    conn.close()
    def mock_connect(read_only=True):
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c
    return db_path, mock_connect

def _patch_environment(tmp_path, monkeypatch):
    db_path, mock_connect = _make_cgvn_db(tmp_path)
    monkeypatch.setattr("data_sources.cvm._db.connect_cgvn", mock_connect)
    monkeypatch.setattr("data_sources.cvm.cgvn.catalog.db_path", lambda: db_path)
    monkeypatch.setattr("data_sources.cvm._db.cgvn_db_path", lambda: db_path)
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                        lambda: Path("/nonexistent/bridge.db"))
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
