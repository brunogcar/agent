"""Tests for the `quarterly` mode of skills/cvm/financials.

Covers:
  - TestQuarterlyMode                   : quarterly() happy path / no-company /
                                           standalone Q2 derivation (3 tests).
  - TestQuarterlyV101Regressions        : v1.0.1 cross-DB empresa_ids fix + Q1
                                           standalone fix (2 tests).

Both classes use the shared `financials_env` fixture from conftest.py. The
v1.0.1 regression `test_cross_database_ids_regression` builds its own
synthetic DBs inline (DFP id=1, ITR id=999 for the same company) to verify
that the skill resolves empresa_ids separately per DB.
"""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm._db import _ensure_schema


# ════════════════════════════════════════════════════════════════════════════
# TestQuarterlyMode
# ════════════════════════════════════════════════════════════════════════════

class TestQuarterlyMode:
    """Tests for `financials.quarterly()`."""

    def test_quarterly_ok(self, financials_env):
        from skills.cvm.financials.financials import quarterly
        result = quarterly(company="33000167000101", periods=8)
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"
        assert len(result["periods"]) >= 1
        # Check that we have quarter labels
        first = result["periods"][0]
        assert "quarter" in first
        assert first["quarter"] in (1, 2, 3, 4)

    def test_quarterly_no_company(self, financials_env):
        from skills.cvm.financials.financials import quarterly
        result = quarterly()
        assert result["status"] == "error"

    def test_quarterly_standalone_derivation(self, financials_env):
        """Verify Q2 standalone = Q2_cumulative - Q1_cumulative."""
        from skills.cvm.financials.financials import quarterly
        result = quarterly(company="33000167000101", periods=8)
        if result["status"] != "ok" or not result["periods"]:
            pytest.skip("Not enough quarterly data")
        # Find Q2 (if available) and verify standalone
        for p in result["periods"]:
            if p["quarter"] == 2:
                # Q2 cumulative = 50% of annual receita = 25B
                # Q1 cumulative = 25% of annual receita = 12.5B
                # Q2 standalone = 25B - 12.5B = 12.5B
                receita_standalone = p["metrics"]["receita_liquida"]
                assert receita_standalone == pytest.approx(12500000000.0, rel=1e-6)
                break


# ════════════════════════════════════════════════════════════════════════════
# v1.0.1 quarterly-mode regression tests
# ════════════════════════════════════════════════════════════════════════════

class TestQuarterlyV101Regressions:
    """[v1.0.1] Quarterly-mode regression tests for bugs found in the
    collective LLM review."""

    def test_cross_database_ids_regression(self, tmp_path: Path, monkeypatch):
        """[P0] DFP and ITR have independent autoincrement IDs.

        The skill must resolve empresa_ids separately for each DB. This test
        uses id=1 in DFP but id=999 in ITR for the same company — before the
        P0 fix, the skill would query ITR with id=1 and find nothing.
        """
        # DFP db: company with id=1
        dfp_path = tmp_path / "dfp.db"
        conn = sqlite3.connect(str(dfp_path))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'TEST CO', 2023, '9512')")
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (1, '1', 'Ativo Total', 'BPA', 1, '', '2023-12-31', 12, 'ÚLTIMO', 1, 100000, 'MIL')")
        conn.commit(); conn.close()

        # ITR db: SAME company but id=999 (different autoincrement!)
        itr_path = tmp_path / "itr.db"
        conn = sqlite3.connect(str(itr_path))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (999, '33000167000101', 'TEST CO', 2023, '9512')")
        # Q1 cumulative (meses=3) for receita
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (999, '3.01', 'Receita', 'DRE', 1, '2023-01-01', '2023-03-31', 3, 'ÚLTIMO', 1, 25000, 'MIL')")
        conn.commit(); conn.close()

        def mock_connect_dfp(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{dfp_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(dfp_path))
            c.row_factory = sqlite3.Row
            return c

        def mock_connect_itr(read_only=True):
            if read_only:
                c = sqlite3.connect(f"file:{itr_path}?mode=ro", uri=True)
            else:
                c = sqlite3.connect(str(itr_path))
            c.row_factory = sqlite3.Row
            return c

        monkeypatch.setattr("data_sources.cvm._db.connect_dfp", mock_connect_dfp)
        monkeypatch.setattr("data_sources.cvm._db.connect_itr", mock_connect_itr)
        monkeypatch.setattr("data_sources.cvm._db.dfp_db_path", lambda: dfp_path)
        monkeypatch.setattr("data_sources.cvm._db.itr_db_path", lambda: itr_path)
        monkeypatch.setattr("data_sources.cvm._bridge.bridge_db_path",
                            lambda: Path("/nonexistent/bridge.db"))
        monkeypatch.setattr("data_sources.cvm._bridge.cad_db_path",
                            lambda: Path("/nonexistent/cad.db"))
        monkeypatch.setattr("data_sources.cvm._bridge._resolve_via_cad",
                            lambda name: (None, None))

        from skills.cvm.financials.financials import quarterly
        result = quarterly(company="33000167000101", periods=8)
        # Before P0 fix: would return empty periods (ITR query with id=1 found nothing)
        # After P0 fix: should find Q1 data from ITR (id=999)
        assert result["status"] == "ok"
        assert len(result["periods"]) >= 1
        # Verify receita_liquida was found (not None) — proves ITR was queried with correct id
        q1 = [p for p in result["periods"] if p["quarter"] == 1]
        if q1:
            assert q1[0]["metrics"]["receita_liquida"] is not None, \
                "ITR data not found — cross-database ID bug not fixed"

    def test_q1_standalone_not_subtracting_prior_year(self, financials_env):
        """[P1] Q1 standalone = Q1 cumulative (NOT cumulative - prior_year_DFP).

        Prior fix: Q1 subtracted prior-year annual total → large negative numbers.
        """
        from skills.cvm.financials.financials import quarterly
        result = quarterly(company="33000167000101", periods=8)
        if result["status"] != "ok":
            pytest.skip("Not enough data")
        # Find Q1 quarters
        q1s = [p for p in result["periods"] if p["quarter"] == 1]
        for q1 in q1s:
            receita = q1["metrics"]["receita_liquida"]
            if receita is not None:
                # Q1 standalone should be POSITIVE (25% of annual in our fixture)
                # Before fix: would be Q1_cum - prior_year_total = huge negative
                assert receita > 0, f"Q1 receita should be positive, got {receita}"
