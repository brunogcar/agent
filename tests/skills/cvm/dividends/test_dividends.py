"""tests/skills/cvm/test_dividends.py -- Tests for the dividends skill.

Mocks B3 dividends + DFP DVA/BPP + CVM IPE query engines — no real DBs, no network.
Tests all 5 modes: history, annual, payable, announcements, summary.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path


# ── B3 dividends mocks ───────────────────────────────────────────────────────

def _mock_b3_history_ok():
    def mock(ticker="", limit=50):
        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "count": 2,
            "dividends": [
                {"ticker": ticker.upper(), "label": "JCP", "isin_code": "BRPETRACNPR6",
                 "approved_on": "2024-08-15", "last_date_prior": "2024-08-10",
                 "rate": 0.35, "related_to": "2T2024", "payment_date": "2024-09-15"},
                {"ticker": ticker.upper(), "label": "Dividendo", "isin_code": "BRPETRACNPR6",
                 "approved_on": "2024-04-15", "last_date_prior": "2024-04-10",
                 "rate": 1.55, "related_to": "1T2024", "payment_date": "2024-05-15"},
            ],
        }
    return mock


def _mock_b3_not_found():
    def mock(ticker="", limit=50):
        return {"status": "not_found", "ticker": ticker, "count": 0, "dividends": []}
    return mock


# ── IPE mock ─────────────────────────────────────────────────────────────────

def _mock_ipe_announcements_ok():
    def mock(company="", categoria="", tipo="", keyword="", data_from="", data_to="", limit=20):
        return {
            "status": "ok",
            "count": 1,
            "events": [{
                "cnpj": "33000167000101", "nome": "PETROLEO BRASILEIRO S.A.",
                "data_entrega": "2024-04-20", "categoria": "Comunicado ao Mercado",
                "tipo": "Aviso aos Acionistas", "assunto": "Distribuição de dividendos",
                "protocolo": "12345",
            }],
        }
    return mock


# ── DFP synthetic DB for annual + payable ────────────────────────────────────

def _make_dfp_db(tmp_path):
    """Create DFP db with DVA 7.08.04.* + BPP 2.01.05.02.* data."""
    from data_sources.cvm._db import _ensure_schema
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
        "VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    conn.execute(
        "INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) "
        "VALUES (2, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2022, '9512')")

    # DVA 7.08.04.* for 2023 (annual, meses=12)
    for code, valor in [("7.08.04", 50000000000), ("7.08.04.01", 15000000000),
                         ("7.08.04.02", 35000000000), ("7.08.04.03", 10000000000)]:
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (1, ?, ?, 'DVA', 1, '2023-01-01', '2023-12-31', 12, 'ÚLTIMO', 1, ?, 1000)",
            (code, f"DVA {code}", valor))

    # DVA 7.08.04.* for 2022
    for code, valor in [("7.08.04", 45000000000), ("7.08.04.02", 30000000000)]:
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (2, ?, ?, 'DVA', 1, '2022-01-01', '2022-12-31', 12, 'ÚLTIMO', 1, ?, 1000)",
            (code, f"DVA {code}", valor))

    # BPP 2.01.05.02.01 (payable) for 2023
    conn.execute(
        "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
        "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
        "VALUES (1, '2.01.05.02.01', 'Dividendos e JCP a Pagar', 'BPP', 1, '', '2023-12-31', 12, 'ÚLTIMO', 1, 5000000000, 1000)")

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
    monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect)
    monkeypatch.setattr("data_sources.cvm._db.dfp_db_path", lambda: db_path)
    monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                        lambda: Path("/nonexistent/bridge.db"))
    monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                        lambda name: (None, None))


# ════════════════════════════════════════════════════════════════════════════
# HISTORY MODE TESTS (B3 dividends)
# ════════════════════════════════════════════════════════════════════════════

class TestHistoryMode:

    def test_history_ok(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", _mock_b3_history_ok())
        from skills.cvm.dividends.dividends import history
        result = history(company="PETR4")
        assert result["status"] == "ok"
        assert result["count"] == 2
        assert result["dividends"][0]["label"] == "JCP"
        assert result["dividends"][1]["label"] == "Dividendo"

    def test_history_no_company(self, monkeypatch):
        from skills.cvm.dividends.dividends import history
        result = history()
        assert result["status"] == "error"

    def test_history_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", _mock_b3_not_found())
        from skills.cvm.dividends.dividends import history
        result = history(company="ZZZZ4")
        assert result["status"] == "not_found"


# ════════════════════════════════════════════════════════════════════════════
# ANNUAL MODE TESTS (DFP DVA 7.08.04.*)
# ════════════════════════════════════════════════════════════════════════════

class TestAnnualMode:

    def test_annual_ok(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.dividends.dividends import annual
        result = annual(company="33000167000101", periods=5)
        assert result["status"] == "ok"
        assert len(result["periods"]) == 2
        # Latest first
        assert result["periods"][0]["data_fim_exerc"] == "2023-12-31"
        accounts = result["periods"][0]["accounts"]
        assert "7.08.04" in accounts  # total
        assert "7.08.04.02" in accounts  # Dividendos
        # valor=35000000000, escala=1000 -> 35 trillion BRL
        assert accounts["7.08.04.02"]["valor_brl"] == 35000000000000.0

    def test_annual_no_company(self, monkeypatch):
        from skills.cvm.dividends.dividends import annual
        result = annual()
        assert result["status"] == "error"

    def test_annual_not_found(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.dividends.dividends import annual
        result = annual(company="NONEXISTENT")
        assert result["status"] == "not_found"


# ════════════════════════════════════════════════════════════════════════════
# PAYABLE MODE TESTS (DFP BPP 2.01.05.02.01)
# ════════════════════════════════════════════════════════════════════════════

class TestPayableMode:

    def test_payable_ok(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.dividends.dividends import payable
        result = payable(company="33000167000101")
        assert result["status"] == "ok"
        assert len(result["periods"]) == 1
        accounts = result["periods"][0]["accounts"]
        assert accounts[0]["codigo"] == "2.01.05.02.01"
        # valor=5000000000, escala=1000 -> 5 trillion BRL
        assert accounts[0]["valor_brl"] == 5000000000000.0

    def test_payable_no_company(self, monkeypatch):
        from skills.cvm.dividends.dividends import payable
        result = payable()
        assert result["status"] == "error"

    def test_payable_not_found(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)

        from skills.cvm.dividends.dividends import payable
        result = payable(company="NONEXISTENT")
        assert result["status"] == "not_found"


# ════════════════════════════════════════════════════════════════════════════
# ANNOUNCEMENTS MODE TESTS (CVM IPE)
# ════════════════════════════════════════════════════════════════════════════

class TestAnnouncementsMode:

    def test_announcements_ok(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.cvm.ipe.query_engine.query", _mock_ipe_announcements_ok())
        from skills.cvm.dividends.dividends import announcements
        result = announcements(company="PETR4")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert "dividendos" in result["events"][0]["assunto"].lower()

    def test_announcements_empty_company(self, monkeypatch):
        """announcements with no company still works (returns all dividend filings)."""
        monkeypatch.setattr(
            "data_sources.cvm.ipe.query_engine.query", _mock_ipe_announcements_ok())
        from skills.cvm.dividends.dividends import announcements
        result = announcements()
        assert result["status"] == "ok"


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryMode:

    def test_summary_all_ok(self, tmp_path, monkeypatch):
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", _mock_b3_history_ok())

        from skills.cvm.dividends.dividends import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        assert "recent_events" in result["sections"]
        assert "annual_trend" in result["sections"]
        assert "payable" in result["sections"]
        assert result["sections"]["recent_events"]["count"] == 2
        assert result["sections"]["annual_trend"]["periods"][0]["data_fim_exerc"] == "2023-12-31"

    def test_summary_b3_missing(self, tmp_path, monkeypatch):
        """If B3 is missing, summary still returns DFP annual + payable."""
        db_path, mock_connect = _make_dfp_db(tmp_path)
        _patch_dfp(monkeypatch, db_path, mock_connect)
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", _mock_b3_not_found())

        from skills.cvm.dividends.dividends import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        assert result["sections"]["recent_events"]["status"] == "not_found"
        assert "annual_trend" in result["sections"]

    def test_summary_no_company(self):
        from skills.cvm.dividends.dividends import summary
        result = summary()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestDividendsRoute:

    def test_route_no_mode(self):
        from skills.cvm.dividends import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.cvm.dividends import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_history(self, monkeypatch):
        monkeypatch.setattr(
            "data_sources.b3.dividends.query_engine.dividends", _mock_b3_history_ok())
        from skills.cvm.dividends import route
        result = route(mode="history", company="PETR4")
        assert result["status"] == "ok"
