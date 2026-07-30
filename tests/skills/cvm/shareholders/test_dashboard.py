"""Tests for skills/cvm/shareholders/ — dashboard mode.

[v1.1] Split out of the original single-file `test_shareholders.py`.
Covers the dashboard mode (multi-tab composition that orchestrates the
underlying summary mode — which itself calls shareholders + free_float +
equity_structure):

  - no company -> short-circuit error
  - basic shape (status, tabs, kpis lists)
  - tab names exactly ['Overview', 'Top Shareholders', 'Free Float',
    'Equity Structure']
  - top-level KPI cards (% Free Float, Total Acionistas, PL Total)
  - degradation when FRE returns not_found (Top Shareholders tab has 0
    rows, Equity Structure tab has 0 rows, all KPIs render '—')
  - route dispatches to dashboard mode

The mock FRE + DFP setup mirrors `test_shareholders.py` (duplicated here
so this test module is self-contained). Each test gets its own synthetic
DFP db via tmp_path so tests don't share DB state.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from skills.cvm.shareholders import MANIFEST, route
from skills.cvm.shareholders.modes.dashboard import dashboard


# ── Helpers (mirror test_shareholders.py — duplicated for self-containment) ──

def _mock_fre_shareholders_ok():
    """Mock FRE shareholders returning PETR4 data."""
    def mock(company="", limit=50):
        return {
            "status": "ok",
            "company": "PETROLEO BRASILEIRO S.A.",
            "cnpj": "33000167000101",
            "data_referencia": "2023-12-31",
            "shareholders": [
                {"acionista": "UNIAO FEDERAL", "cpf_cnpj": "00000000000001",
                 "tipo_pessoa": "PJ", "controlador": "S",
                 "pct_on": 36.7, "pct_pn": 0.0, "pct_total": 28.9,
                 "qtd_on": 5000000000, "qtd_pn": 0, "qtd_total": 5000000000},
                {"acionista": "BLACKROCK INC", "cpf_cnpj": "00000000000002",
                 "tipo_pessoa": "PJ", "controlador": "N",
                 "pct_on": 0.0, "pct_pn": 5.0, "pct_total": 3.0,
                 "qtd_on": 0, "qtd_pn": 300000000, "qtd_total": 300000000},
            ],
        }
    return mock


def _mock_fre_free_float_ok():
    def mock(company=""):
        return {
            "status": "ok",
            "company": "PETROLEO BRASILEIRO S.A.",
            "cnpj": "33000167000101",
            "periods": [{
                "data_referencia": "2023-12-31",
                "pct_on_circulacao": 63.3,
                "pct_pn_circulacao": 100.0,
                "pct_total_circulacao": 71.1,
                "qtd_on_circulacao": 8500000000,
                "qtd_pn_circulacao": 6000000000,
                "qtd_total_circulacao": 14500000000,
                "qtd_acionistas_pf": 250000,
                "qtd_acionistas_pj": 500,
                "qtd_acionistas_inst": 120,
                "data_ultima_assembleia": "2024-04-30",
            }],
        }
    return mock


def _mock_fre_not_found():
    def mock(company="", **kw):
        return {"status": "not_found", "error": f"No data for '{company}'"}
    return mock


# ── DFP synthetic DB for equity_structure ────────────────────────────────────

def _make_dfp_db(tmp_path):
    """Create a synthetic DFP db with BPP 2.03.* equity data."""
    from data_sources.cvm._db import _ensure_schema
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    # PETROBRAS: cnpj=33000167000101, cd_cvm=9512
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
        "VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
        "VALUES (2, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2022, '9512')")
    # BPP 2.03.* for 2023
    for code, valor in [("2.03", 500000000000), ("2.03.01", 200000000000),
                         ("2.03.02", 5000000000), ("2.03.04", 100000000000),
                         ("2.03.05", 145000000000), ("2.03.09", 50000000000)]:
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (1, ?, ?, 'BPP', 1, '', '2023-12-31', 12, 'ÚLTIMO', 1, ?, 1000)",
            (code, f"Account {code}", valor))
    # BPP 2.03.* for 2022
    for code, valor in [("2.03", 450000000000), ("2.03.01", 190000000000)]:
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (2, ?, ?, 'BPP', 1, '', '2022-12-31', 12, 'ÚLTIMO', 1, ?, 1000)",
            (code, f"Account {code}", valor))
    conn.commit()
    conn.close()

    def mock_connect(read_only=True):
        if read_only:
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c
    return db_path, mock_connect


def _patch_dfp(monkeypatch, db_path, mock_connect):
    """Patch DFP connection + bridge to use synthetic db."""
    monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect)
    monkeypatch.setattr("data_sources.cvm._db.dfp_db_path", lambda: db_path)
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                        lambda: Path("/nonexistent/bridge.db"))
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                        lambda name: (None, None))


def _patch_all_ok(tmp_path, monkeypatch):
    """Happy-path setup: DFP db + FRE shareholders + free_float all returning
    PETR4 data. Used by the dashboard tests for the non-degraded path."""
    db_path, mock_connect = _make_dfp_db(tmp_path)
    _patch_dfp(monkeypatch, db_path, mock_connect)
    monkeypatch.setattr(
        "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_shareholders_ok())
    monkeypatch.setattr(
        "data_sources.cvm.fre.query_engine.free_float", _mock_fre_free_float_ok())


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company -> status=error with 'company is required'.

        The dashboard short-circuits before any underlying skill is called.
        """
        r = dashboard()
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dashboard_basic_shape(self, tmp_path, monkeypatch):
        """Dashboard returns status=ok with top-level tabs + kpis lists."""
        _patch_all_ok(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert r["status"] == "ok"
        assert "tabs" in r
        assert "kpis" in r
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_tab_names(self, tmp_path, monkeypatch):
        """Tabs are exactly ['Overview', 'Top Shareholders', 'Free Float',
        'Equity Structure']."""
        _patch_all_ok(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Top Shareholders", "Free Float",
                         "Equity Structure"]
        # Each tab has a non-empty sections list.
        for t in r["tabs"]:
            assert isinstance(t["sections"], list)
            assert len(t["sections"]) >= 1

    def test_dashboard_top_level_kpis(self, tmp_path, monkeypatch):
        """3 KPI cards at the top level with exact labels + unit fields."""
        _patch_all_ok(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert len(r["kpis"]) == 3
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["% Free Float", "Total Acionistas", "PL Total"]
        # Each KPI has label + value + unit.
        for k in r["kpis"]:
            assert "label" in k
            assert "value" in k
            assert "unit" in k

    def test_dashboard_degrades_when_summary_fails(self, tmp_path, monkeypatch):
        """When FRE returns not_found for all 3 sections (shareholders,
        free_float, equity_structure), summary() still returns status=ok with
        error payloads per section — the dashboard still renders status=ok
        with 4 tabs (Top Shareholders tab has 0 rows, Free Float tab has 1
        row of None values, Equity Structure tab has 0 rows, all KPIs render
        as '—')."""
        # Patch DFP to point at an empty db (no empresas) + FRE returns
        # not_found for both shareholders + free_float.
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_not_found())
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.free_float", _mock_fre_not_found())

        r = dashboard(company="UNKNOWN4")
        assert r["status"] == "ok"
        assert len(r["tabs"]) == 4
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Top Shareholders", "Free Float",
                         "Equity Structure"]
        # All KPIs render as dash (no free float data, no equity data).
        for kpi in r["kpis"]:
            assert kpi["value"] == "—"
        # Top Shareholders tab has 0 rows (no 'top' list in section).
        ts_tab = next(t for t in r["tabs"] if t["name"] == "Top Shareholders")
        ts_sec = ts_tab["sections"][0]
        assert len(ts_sec["rows"]) == 0
        # Equity Structure tab has 0 rows (no 'components' dict).
        eq_tab = next(t for t in r["tabs"] if t["name"] == "Equity Structure")
        eq_sec = eq_tab["sections"][0]
        assert len(eq_sec["rows"]) == 0

    def test_route_dispatches_dashboard_mode(self):
        """route(mode='dashboard') with no company returns status=error with
        'company is required' (short-circuits in dashboard())."""
        assert "dashboard" in MANIFEST["modes"]
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "company is required" in r["error"]
