"""Tests for dividends dashboard mode."""
from __future__ import annotations
import pytest
from skills.cvm.dividends.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self):
        r = dashboard()
        assert r["status"] == "error"

    def test_dashboard_tab_structure(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch, b3_mock=_mock_b3_history_ok())
        r = dashboard(company="33000167000101")
        assert r["status"] == "ok"
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "History", "Annual"]

    def test_dashboard_top_level_kpis(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch, b3_mock=_mock_b3_history_ok())
        r = dashboard(company="33000167000101")
        assert len(r["kpis"]) == 4
        labels = [k["label"] for k in r["kpis"]]
        assert "Total Dividends Paid" in labels
        assert "Dividend Yield" in labels
        assert "Payout Ratio" in labels
        assert "Last Payment Date" in labels

    def test_dashboard_dividend_yield_has_value(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch, b3_mock=_mock_b3_history_ok())
        r = dashboard(company="33000167000101")
        kpi = next(k for k in r["kpis"] if k["label"] == "Dividend Yield")
        assert kpi["value"] == "11,69%"

    def test_dashboard_payout_ratio_has_value(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch, b3_mock=_mock_b3_history_ok())
        r = dashboard(company="33000167000101")
        kpi = next(k for k in r["kpis"] if k["label"] == "Payout Ratio")
        assert kpi["value"] != "—"


# ── Helpers (from original test file) ────────────────────────────────────────
import sqlite3
from pathlib import Path

def _mock_b3_history_ok():
    def mock(ticker="", limit=50):
        return {"status": "ok", "events": [
            {"ticker": "PETR4", "type": "dividendo", "value": 4.5, "date": "2024-08-20", "payment_date": "2026-08-20"},
        ]}
    return mock

def _make_dfp_db(tmp_path):
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE contas (codigo TEXT, descricao TEXT, grupo TEXT,
        data_fim_exerc TEXT, valor REAL, escala TEXT, meses INTEGER,
        consolidado INTEGER, id_empresa INTEGER)""")
    conn.execute("""CREATE TABLE empresas (id INTEGER PRIMARY KEY, ano INTEGER,
        cd_cvm TEXT, nome TEXT)""")
    conn.execute("INSERT INTO empresas VALUES (1, 2023, '9512', 'PETROBRAS')")
    conn.execute("""INSERT INTO contas VALUES ('7.08.04', 'Dividendos', 'DVA',
        '2023-12-31', 50000000000, 'MIL', 12, 1, 1)""")
    conn.commit()
    conn.close()
    def mock_connect(read_only=True):
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c
    return db_path, mock_connect

def _patch_dfp(monkeypatch, db_path, mock_connect):
    monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect)
    monkeypatch.setattr("data_sources.cvm._db.dfp_db_path", lambda: db_path)
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                        lambda: Path("/nonexistent/bridge.db"))
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                        lambda name: (None, None))

def _patch_environment(tmp_path, monkeypatch, b3_mock=None):
    db_path, mock_connect = _make_dfp_db(tmp_path)
    _patch_dfp(monkeypatch, db_path, mock_connect)
    if b3_mock is not None:
        monkeypatch.setattr("data_sources.b3.dividends.query_engine.dividends", b3_mock)
    monkeypatch.setattr("skills.cvm.dividends.report.dividends_at", lambda c, d: 4.5)
    monkeypatch.setattr("skills.cvm.dividends.report.price_at", lambda c, d: 38.5)
    monkeypatch.setattr("skills.cvm.dividends.report.ttm_earnings_at", lambda c, d: 110e9)
    monkeypatch.setattr("skills.cvm.dividends.report.shares_at", lambda c, d: 13e9)
