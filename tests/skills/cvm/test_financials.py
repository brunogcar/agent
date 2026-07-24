"""tests/skills/cvm/test_financials.py -- Tests for the financials skill.

Uses synthetic DFP + ITR SQLite DBs with realistic account data.
Tests all 4 modes: quarterly, annual, complete, summary.
Also tests metrics.py: standalone quarter derivation + ratio computation.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from data_sources.cvm._db import _ensure_schema


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_dfp_db(tmp_path):
    """Create synthetic DFP db with annual data (meses=12) for 2023 + 2022."""
    db_path = tmp_path / "dfp.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    # Company: PETROBRAS, cnpj=33000167000101, cd_cvm=9512
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (2, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2022, '9512')")
    # 2023 annual values (valor in thousands, escala="MIL")
    vals_2023 = {
        "1": 100000000, "1.01.01": 20000000, "2": 100000000, "2.03": 40000000,
        "2.01.04": 15000000, "2.02.01": 25000000,
        "3.01": 50000000, "3.03": 30000000, "3.05": 20000000, "3.06": -5000000,
        "3.11": 12000000,
        "6.01": 18000000, "6.02": -8000000, "6.03": -5000000, "6.01.01.02": 3000000,
        "7.08.04": 6000000,
    }
    for code, val in vals_2023.items():
        grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (1, ?, ?, ?, 1, '2023-01-01', '2023-12-31', 12, 'ÚLTIMO', 1, ?, 'MIL')",
            (code, f"Account {code}", grupo, val))
    # 2022 annual values (smaller, for trend)
    vals_2022 = {"1": 90000000, "2.03": 35000000, "3.01": 45000000, "3.11": 10000000}
    for code, val in vals_2022.items():
        grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE"
        conn.execute(
            "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
            "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
            "VALUES (2, ?, ?, ?, 1, '2022-01-01', '2022-12-31', 12, 'ÚLTIMO', 1, ?, 'MIL')",
            (code, f"Account {code}", grupo, val))
    conn.commit()
    conn.close()
    return db_path


def _make_itr_db(tmp_path):
    """Create synthetic ITR db with cumulative quarterly data for 2023."""
    db_path = tmp_path / "itr.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    # Same company, 2023 quarterly
    conn.execute("INSERT INTO empresas (id, cnpj, nome, ano, cd_cvm) VALUES (1, '33000167000101', 'PETROLEO BRASILEIRO S.A.', 2023, '9512')")
    # Q1 cumulative (meses=3): 25% of annual for flows, snapshot at Mar 31
    # Q2 cumulative (meses=6): 50% of annual for flows, snapshot at Jun 30
    # Q3 cumulative (meses=9): 75% of annual for flows, snapshot at Sep 30
    annual_vals = {
        "1": 100000000, "1.01.01": 20000000, "2": 100000000, "2.03": 40000000,
        "2.01.04": 15000000, "2.02.01": 25000000,
        "3.01": 50000000, "3.03": 30000000, "3.05": 20000000, "3.06": -5000000,
        "3.11": 12000000,
        "6.01": 18000000, "6.02": -8000000, "6.03": -5000000, "6.01.01.02": 3000000,
        "7.08.04": 6000000,
    }
    for meses, pct, date_end in [(3, 0.25, "2023-03-31"), (6, 0.50, "2023-06-30"), (9, 0.75, "2023-09-30")]:
        for code, annual_val in annual_vals.items():
            grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
            # Snapshots use the period-end value (same as annual for simplicity)
            # Flows use cumulative (pct * annual)
            is_snapshot = grupo in ("BPA", "BPP")
            val = annual_val if is_snapshot else int(annual_val * pct)
            data_ini = "" if is_snapshot else "2023-01-01"
            conn.execute(
                "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
                "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
                "VALUES (1, ?, ?, ?, 1, ?, ?, 12, 'ÚLTIMO', 1, ?, 'MIL')",
                (code, f"Account {code}", grupo, data_ini, date_end, val))
    # Fix: meses should match the quarter, not always 12
    # Actually the _ensure_schema sets meses via the INSERT. Let me fix.
    conn.close()
    # Re-do with correct meses
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM contas")
    for meses, pct, date_end in [(3, 0.25, "2023-03-31"), (6, 0.50, "2023-06-30"), (9, 0.75, "2023-09-30")]:
        for code, annual_val in annual_vals.items():
            grupo = "BPA" if code.startswith("1") else "BPP" if code.startswith("2") else "DRE" if code.startswith("3") else "DFC_MI" if code.startswith("6") else "DVA"
            is_snapshot = grupo in ("BPA", "BPP")
            val = annual_val if is_snapshot else int(annual_val * pct)
            data_ini = "" if is_snapshot else "2023-01-01"
            conn.execute(
                "INSERT INTO contas (id_empresa, codigo, descricao, grupo, consolidado, "
                "data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao, valor, escala) "
                "VALUES (1, ?, ?, ?, 1, ?, ?, ?, 'ÚLTIMO', 1, ?, 'MIL')",
                (code, f"Account {code}", grupo, data_ini, date_end, meses, val))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def financials_env(tmp_path, monkeypatch):
    """Set up synthetic DFP + ITR DBs and patch all paths."""
    dfp_path = _make_dfp_db(tmp_path)
    itr_path = _make_itr_db(tmp_path)

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
    return dfp_path, itr_path


# ════════════════════════════════════════════════════════════════════════════
# METRICS.PY TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestMetrics:

    def test_compute_ebitda(self):
        """[v1.0.1] compute_ebitda now returns (value, method) tuple."""
        from skills.cvm.financials.metrics import compute_ebitda
        assert compute_ebitda(20000000, 3000000) == (23000000, "ebit+da")
        assert compute_ebitda(20000000, None) == (20000000, "ebit_only")
        assert compute_ebitda(None, 3000000) == (None, "none")

    def test_compute_ratios_annual(self):
        from skills.cvm.financials.metrics import compute_ratios
        metrics = {
            "receita_liquida": 50000000, "lucro_bruto": 30000000,
            "ebit": 20000000, "ebitda": 23000000, "lucro_liquido": 12000000,
            "ativo_total": 100000000, "patrimonio_liquido": 40000000,
            "caixa": 20000000, "divida_bruta": 40000000, "proventos": 6000000,
        }
        r = compute_ratios(metrics, is_quarterly=False)
        assert r["marg_bruta"] == 0.6  # 30M / 50M
        assert r["marg_ebitda"] == 0.46  # 23M / 50M
        assert r["marg_ebit"] == 0.4  # 20M / 50M
        assert r["marg_liquida"] == 0.24  # 12M / 50M
        assert r["roa"] == 0.12  # 12M / 100M
        assert r["roe"] == 0.3  # 12M / 40M
        assert r["divida_bruta_pl"] == 1.0  # 40M / 40M
        assert r["divida_liquida"] == 20000000  # 40M - 20M
        assert r["payout"] == 0.5  # 6M / 12M

    def test_compute_ratios_quarterly_annualized(self):
        from skills.cvm.financials.metrics import compute_ratios
        metrics = {
            "lucro_liquido": 3000000, "ativo_total": 100000000,
            "patrimonio_liquido": 40000000, "receita_liquida": 12500000,
        }
        r = compute_ratios(metrics, is_quarterly=True)
        # ROA annualized = (3M * 4) / 100M = 0.12
        assert r["roa"] == pytest.approx(0.12)
        # ROE annualized = (3M * 4) / 40M = 0.3
        assert r["roe"] == pytest.approx(0.3)

    def test_compute_ratios_quarterly_payout_none(self):
        """[v1.0.1] Payout = None in quarterly mode (DVA is annual-only)."""
        from skills.cvm.financials.metrics import compute_ratios
        metrics = {
            "lucro_liquido": 3000000, "receita_liquida": 12500000,
            "proventos": 6000000,
        }
        r = compute_ratios(metrics, is_quarterly=True)
        assert r["payout"] is None
        # Annual mode should still compute payout
        r_annual = compute_ratios(metrics, is_quarterly=False)
        assert r_annual["payout"] is not None

    def test_compute_ratios_negative_pl_guard(self):
        """[v1.0.1] ROE + debt/PL ratios = None when PL <= 0 (accumulated losses)."""
        from skills.cvm.financials.metrics import compute_ratios
        metrics = {
            "lucro_liquido": 5000000, "ativo_total": 100000000,
            "patrimonio_liquido": -10000000,  # negative PL
            "divida_bruta": 40000000, "caixa": 5000000,
        }
        r = compute_ratios(metrics, is_quarterly=False)
        assert r["roe"] is None  # negative PL → ROE meaningless
        assert r["divida_bruta_pl"] is None
        assert r["divida_liquida_pl"] is None
        # ROA should still work (doesn't use PL)
        assert r["roa"] is not None

    def test_compute_ratios_none_values(self):
        from skills.cvm.financials.metrics import compute_ratios
        r = compute_ratios({}, is_quarterly=False)
        assert r["marg_bruta"] is None
        assert r["roa"] is None

    def test_compute_ttm_ebitda(self):
        from skills.cvm.financials.metrics import compute_ttm_ebitda
        # 4 quarters: 10 + 20 + 30 + 40 = 100
        assert compute_ttm_ebitda([40, 30, 20, 10]) == 100
        # Only 3 quarters → None
        assert compute_ttm_ebitda([30, 20, 10]) is None
        # Empty → None
        assert compute_ttm_ebitda([]) is None


# ════════════════════════════════════════════════════════════════════════════
# ANNUAL MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestAnnualMode:

    def test_annual_ok(self, financials_env):
        from skills.cvm.financials.financials import annual
        result = annual(company="33000167000101", periods=5)
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert len(result["periods"]) == 2  # 2023 + 2022
        # Latest first
        assert result["periods"][0]["period"] == "2023"
        metrics = result["periods"][0]["metrics"]
        # valor=100000000, escala="MIL" → 100 billion
        assert metrics["ativo_total"] == 100000000000.0
        assert metrics["receita_liquida"] == 50000000000.0
        # EBITDA = EBIT (20B) + D&A (3B) = 23B
        assert metrics["ebitda"] == 23000000000.0
        ratios = result["periods"][0]["ratios"]
        assert ratios["marg_bruta"] == 0.6
        assert ratios["roe"] == 0.3

    def test_annual_no_company(self, financials_env):
        from skills.cvm.financials.financials import annual
        result = annual()
        assert result["status"] == "error"

    def test_annual_not_found(self, financials_env):
        from skills.cvm.financials.financials import annual
        result = annual(company="NONEXISTENT")
        assert result["status"] == "not_found"


# ════════════════════════════════════════════════════════════════════════════
# QUARTERLY MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestQuarterlyMode:

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
# COMPLETE MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestCompleteMode:

    def test_complete_annual_ok(self, financials_env):
        from skills.cvm.financials.financials import complete
        result = complete(company="33000167000101", period="annual", grupo="DRE")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["grupo_filter"] == "DRE"
        # Should have DRE key codes
        codes_found = {a["codigo"] for p in result["periods"] for a in p["accounts"]}
        assert "3.01" in codes_found  # Receita Líquida

    def test_complete_quarterly_ok(self, financials_env):
        from skills.cvm.financials.financials import complete
        result = complete(company="33000167000101", period="quarterly", grupo="BPA")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"

    def test_complete_no_grupo_all_codes(self, financials_env):
        from skills.cvm.financials.financials import complete
        result = complete(company="33000167000101", period="annual")
        assert result["status"] == "ok"
        assert result["grupo_filter"] == "all"

    def test_complete_unknown_grupo(self, financials_env):
        from skills.cvm.financials.financials import complete
        result = complete(company="33000167000101", grupo="INVALID")
        assert result["status"] == "error"

    def test_complete_no_company(self, financials_env):
        from skills.cvm.financials.financials import complete
        result = complete()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY MODE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryMode:

    def test_summary_ok(self, financials_env):
        from skills.cvm.financials.financials import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        assert "latest_annual" in result["sections"]
        assert "latest_quarterly" in result["sections"]

    def test_summary_no_company(self, financials_env):
        from skills.cvm.financials.financials import summary
        result = summary()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestFinancialsRoute:

    def test_route_no_mode(self):
        from skills.cvm.financials import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.cvm.financials import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_annual(self, financials_env):
        from skills.cvm.financials import route
        result = route(mode="annual", company="33000167000101")
        assert result["status"] == "ok"


# ════════════════════════════════════════════════════════════════════════════
# V1.0.1 REGRESSION TESTS (cross-database IDs + Q1 fix + summary latest)
# ════════════════════════════════════════════════════════════════════════════

class TestV101Regressions:
    """[v1.0.1] Regression tests for bugs found in the collective LLM review."""

    def test_cross_database_ids_regression(self, tmp_path, monkeypatch):
        """[P0] DFP and ITR have independent autoincrement IDs.
        The skill must resolve empresa_ids separately for each DB.
        This test uses id=1 in DFP but id=999 in ITR for the same company.
        """
        # DFP db: company with id=1
        from data_sources.cvm._db import _ensure_schema
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

    def test_summary_latest_quarterly_is_newest(self, financials_env):
        """[P1] summary.latest_quarterly should be the NEWEST quarter, not oldest."""
        from skills.cvm.financials.financials import summary
        result = summary(company="33000167000101")
        if result["sections"].get("latest_quarterly", {}).get("period"):
            latest = result["sections"]["latest_quarterly"]
            trend = result["sections"].get("quarterly_trend", [])
            if trend:
                # latest should be the last in the trend (newest, since sorted oldest-first)
                assert latest["period"] == trend[-1]["period"], \
                    f"latest_quarterly={latest['period']} should be {trend[-1]['period']} (newest)"

    def test_ebitda_method_provenance(self, financials_env):
        """[v1.0.1] EBITDA response includes ebitda_method field."""
        from skills.cvm.financials.financials import annual
        result = annual(company="33000167000101", periods=2)
        if result["status"] == "ok" and result["periods"]:
            metrics = result["periods"][0]["metrics"]
            assert "ebitda_method" in metrics
            assert metrics["ebitda_method"] in ("ebit+da", "ebit_only", "none")
