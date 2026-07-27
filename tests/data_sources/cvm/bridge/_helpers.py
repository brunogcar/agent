"""tests/data_sources/cvm/bridge/_helpers.py -- Helper functions for bridge tests.

These are module-level helpers (NOT pytest fixtures) extracted from the
original test_bridge.py. They are imported explicitly by the per-class test
modules under tests/data_sources/cvm/bridge/.

Keeping them in a separate module (rather than in conftest.py) makes the
imports explicit and avoids relying on conftest auto-discovery for non-fixture
helpers.
"""
from __future__ import annotations

import sqlite3


def _insert_bridge_row(db_path, ticker, issuing, cd_cvm, trading_name, cnpj,
                       denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at):
    """Helper to insert a row directly into bridge.db."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, cnpj, "
        "denom_social, denom_comerc, sit, setor_ativ, tp_merc, synced_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ticker, issuing, cd_cvm, trading_name, cnpj, denom_social,
         denom_comerc, sit, setor_ativ, tp_merc, synced_at),
    )
    conn.commit()
    conn.close()


# ── Mock factories for dividends + CAD ───────────────────────────────────────

def _mock_dividends_ok(code_cvm, trading_name="TESTCO"):
    """Return a mock for dividends sync + company_info that succeeds."""
    def mock_sync(ticker="", force=False, trace_id=""):
        return {"status": "ok", "ticker": ticker, "cash_count": 1,
                "stock_count": 0, "sub_count": 0}
    def mock_company_info(ticker=""):
        return {"status": "ok", "ticker": ticker,
                "info": {"code_cvm": code_cvm, "trading_name": trading_name}}
    return mock_sync, mock_company_info


def _mock_dividends_no_cvm():
    """Dividends sync succeeds but company_info has no codeCVM."""
    def mock_sync(ticker="", force=False, trace_id=""):
        return {"status": "ok", "ticker": ticker}
    def mock_company_info(ticker=""):
        return {"status": "ok", "ticker": ticker,
                "info": {"code_cvm": "", "trading_name": "NO-CVM-CO"}}
    return mock_sync, mock_company_info


def _mock_dividends_error():
    """Dividends sync returns error."""
    def mock_sync(ticker="", force=False, trace_id=""):
        return {"status": "error", "ticker": ticker, "error": "API down"}
    def mock_company_info(ticker=""):
        return {"status": "not_found", "ticker": ticker}
    return mock_sync, mock_company_info


def _mock_cad_ok(cnpj, denom_social, denom_comerc, sit="ATIVO",
                 setor_ativ="Petróleo", tp_merc="Bolsa", cd_cvm_val="9512"):
    """CAD lookup succeeds. Includes CD_CVM (needed by ISIN fallback path).

    NOTE: uses **kwargs so any combination of cnpj/cd_cvm/name keyword args
    from the real lookup() signature works without TypeError.
    """
    def mock_lookup(**kwargs):
        return {"status": "ok", "company": {
            "CNPJ_CIA": cnpj, "DENOM_SOCIAL": denom_social,
            "DENOM_COMERC": denom_comerc, "SIT": sit,
            "SETOR_ATIV": setor_ativ, "TP_MERC": tp_merc,
            "CD_CVM": cd_cvm_val,
        }}
    return mock_lookup


def _mock_cad_miss():
    """CAD lookup returns not_found."""
    def mock_lookup(**kwargs):
        return {"status": "not_found"}
    return mock_lookup


def _patch_dividends(monkeypatch, mock_sync, mock_company_info):
    monkeypatch.setattr("data_sources.b3.dividends.sync_engine.sync", mock_sync)
    monkeypatch.setattr("data_sources.b3.dividends.query_engine.company_info", mock_company_info)


def _patch_cad(monkeypatch, mock_lookup):
    monkeypatch.setattr("data_sources.cvm.cad.query_engine.lookup", mock_lookup)


def _patch_fca_miss(monkeypatch):
    """[v1.3] Mock _try_fca_resolution to return empty — simulates FCA not synced.

    Without this, tests running on a machine with a real fca.db will have FCA
    resolve the ticker before the mocked dividends/CAD/ISIN paths are reached.
    """
    monkeypatch.setattr(
        "data_sources.cvm.bridge.sync_engine._try_fca_resolution",
        lambda ticker: {"cnpj": ""},
    )
