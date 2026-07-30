"""Tests for governance dashboard mode."""
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

    def test_dashboard_top_level_kpis(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert len(r["kpis"]) == 3
        labels = [k["label"] for k in r["kpis"]]
        assert "Governance Score" in labels
        assert "Practices Count" in labels
        assert "Compliance Level" in labels

    def test_dashboard_governance_score_kpi(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        kpi = next(k for k in r["kpis"] if k["label"] == "Governance Score")
        assert kpi["unit"] == "pct"

    def test_dashboard_compliance_level(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        kpi = next(k for k in r["kpis"] if k["label"] == "Compliance Level")
        assert kpi["unit"] == "text"


# ── Helpers ──────────────────────────────────────────────────────────────────
import sqlite3
from pathlib import Path

def _make_cgvn_db(tmp_path):
    db_path = tmp_path / "cgvn.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE contas (codigo TEXT, descricao TEXT, grupo TEXT,
        data_fim_exerc TEXT, valor TEXT, meses INTEGER, consolidado INTEGER,
        id_empresa INTEGER)""")
    conn.execute("""CREATE TABLE empresas (id INTEGER PRIMARY KEY, cd_cvm TEXT, nome TEXT)""")
    conn.execute("INSERT INTO empresas VALUES (1, '9512', 'PETROBRAS')")
    conn.execute("""INSERT INTO contas VALUES ('1', 'Pratica', 'CGVN',
        '2023-12-31', 'Sim', 12, 1, 1)""")
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
