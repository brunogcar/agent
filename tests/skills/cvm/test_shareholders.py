"""tests/skills/cvm/test_shareholders.py -- Tests for the shareholders skill.

Mocks the underlying data_source query engines (FRE, DFP) — no real DBs, no network.
Tests all 4 modes: shareholders, free_float, equity_structure, summary.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch


# ── Helpers ──────────────────────────────────────────────────────────────────

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
    # resolve_company needs to find the empresa by CNPJ (formatted in db or not)
    # Our db uses normalized CNPJ, so resolver will match directly
    # But _resolve_via_bridge returns (None, None) since no bridge.db
    # So we need to query by CNPJ: resolve_company step 2


# ════════════════════════════════════════════════════════════════════════════
# SHAREHOLDERS MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestShareholdersMode:

    def test_shareholders_ok(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_shareholders_ok())
        from skills.cvm.shareholders.shareholders import shareholders
        result = shareholders(company="PETR4")
        assert result["status"] == "ok"
        assert result["cnpj"] == "33000167000101"
        assert len(result["shareholders"]) == 2
        assert result["shareholders"][0]["acionista"] == "UNIAO FEDERAL"
        assert result["shareholders"][0]["pct_total"] == 28.9

    def test_shareholders_no_company(self, monkeypatch):
        from skills.cvm.shareholders.shareholders import shareholders
        result = shareholders()
        assert result["status"] == "error"

    def test_shareholders_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_not_found())
        from skills.cvm.shareholders.shareholders import shareholders
        result = shareholders(company="ZZZZ4")
        assert result["status"] == "not_found"


# ════════════════════════════════════════════════════════════════════════════
# FREE_FLOAT MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestFreeFloatMode:

    def test_free_float_ok(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.free_float", _mock_fre_free_float_ok())
        from skills.cvm.shareholders.shareholders import free_float
        result = free_float(company="PETR4")
        assert result["status"] == "ok"
        assert result["periods"][0]["pct_total_circulacao"] == 71.1
        assert result["periods"][0]["qtd_acionistas_pf"] == 250000

    def test_free_float_no_company(self, monkeypatch):
        from skills.cvm.shareholders.shareholders import free_float
        result = free_float()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# EQUITY_STRUCTURE MODE TESTS (DFP BPP 2.03.*)
# ════════════════════════════════════════════════════════════════════════════

class TestEquityStructureMode:

    def test_equity_structure_ok(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.shareholders.shareholders import equity_structure
        # Query by CNPJ (normalized) — resolver step 2 finds it
        result = equity_structure(company="33000167000101", periods=5)
        assert result["status"] == "ok"
        assert len(result["periods"]) == 2  # 2023 + 2022
        # Latest period first
        assert result["periods"][0]["data_fim_exerc"] == "2023-12-31"
        accounts = result["periods"][0]["accounts"]
        assert "2.03" in accounts  # total PL
        # valor=500000000000, escala=1000 -> 500 billion BRL
        assert accounts["2.03"]["valor_brl"] == 500000000000000.0

    def test_equity_structure_no_company(self, monkeypatch):
        from skills.cvm.shareholders.shareholders import equity_structure
        result = equity_structure()
        assert result["status"] == "error"

    def test_equity_structure_not_found(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.shareholders.shareholders import equity_structure
        result = equity_structure(company="NONEXISTENT")
        assert result["status"] == "not_found"

    def test_equity_structure_periods_limit(self, tmp_path, monkeypatch):
        """periods=1 should return only the most recent year."""
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.shareholders.shareholders import equity_structure
        result = equity_structure(company="33000167000101", periods=1)
        assert result["status"] == "ok"
        assert len(result["periods"]) == 1
        assert result["periods"][0]["data_fim_exerc"] == "2023-12-31"


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryMode:

    def test_summary_all_ok(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_shareholders_ok())
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.free_float", _mock_fre_free_float_ok())

        from skills.cvm.shareholders.shareholders import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        assert "shareholders" in result["sections"]
        assert "free_float" in result["sections"]
        assert "equity" in result["sections"]
        assert result["sections"]["shareholders"]["top"][0]["acionista"] == "UNIAO FEDERAL"
        assert result["sections"]["equity"]["patrimonio_liquido_total"] == 500000000000000.0

    def test_summary_partial_fre_missing(self, tmp_path, monkeypatch):
        """If FRE is missing, summary still returns DFP equity."""
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_not_found())
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.free_float", _mock_fre_not_found())

        from skills.cvm.shareholders.shareholders import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        assert result["sections"]["shareholders"]["status"] == "not_found"
        assert result["sections"]["equity"]["patrimonio_liquido_total"] == 500000000000000.0

    def test_summary_no_company(self):
        from skills.cvm.shareholders.shareholders import summary
        result = summary()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestShareholdersRoute:

    def test_route_no_mode(self):
        from skills.cvm.shareholders import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.cvm.shareholders import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_shareholders(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.cvm.fre.query_engine.shareholders", _mock_fre_shareholders_ok())
        from skills.cvm.shareholders import route
        result = route(mode="shareholders", company="PETR4")
        assert result["status"] == "ok"
