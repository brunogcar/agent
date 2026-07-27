"""Tests for skills/cvm/financials/metrics.py.

Covers:
  - TestMetrics         : compute_ebitda + compute_ratios (annual / quarterly /
                          negative PL / None values) — 7 tests.
  - TestTTM             : compute_ttm (insufficient data / 4Q sums flows /
                          missing metric → None) — 4 tests.
  - TestDFCMDFallback   : _extract_metrics D&A fallback chain
                          (DFC_MI 6.01.01.02 → DFC_MD 6.02.01.02 → 6.01.04 →
                          None) + EBITDA with direct-method D&A — 5 tests.

Pure-Python tests — no DB fixture required.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# compute_ebitda + compute_ratios
# ════════════════════════════════════════════════════════════════════════════

class TestMetrics:
    """Tests for compute_ebitda() + compute_ratios() in metrics.py."""

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
# compute_ttm (trailing twelve months)
# ════════════════════════════════════════════════════════════════════════════

class TestTTM:
    """v1.1 — TTM (trailing twelve months) computation."""

    def test_ttm_insufficient_data(self):
        from skills.cvm.financials.metrics import compute_ttm
        r = compute_ttm([])
        assert r["status"] == "insufficient_data"

    def test_ttm_three_quarters_insufficient(self):
        from skills.cvm.financials.metrics import compute_ttm
        r = compute_ttm([{"period": "1T", "year": 2025, "quarter": 1,
                          "metrics": {"receita_liquida": 100}, "ratios": {}}])
        assert r["status"] == "insufficient_data"

    def test_ttm_four_quarters_sums_flows(self):
        from skills.cvm.financials.metrics import compute_ttm
        periods = [
            {"period": "1T2024", "year": 2024, "quarter": 1,
             "metrics": {"receita_liquida": 100, "ebitda": 25, "lucro_liquido": 15,
                         "ativo_total": 400, "patrimonio_liquido": 200}},
            {"period": "2T2024", "year": 2024, "quarter": 2,
             "metrics": {"receita_liquida": 110, "ebitda": 28, "lucro_liquido": 16,
                         "ativo_total": 420, "patrimonio_liquido": 210}},
            {"period": "3T2024", "year": 2024, "quarter": 3,
             "metrics": {"receita_liquida": 120, "ebitda": 30, "lucro_liquido": 18,
                         "ativo_total": 440, "patrimonio_liquido": 215}},
            {"period": "4T2024", "year": 2024, "quarter": 4,
             "metrics": {"receita_liquida": 130, "ebitda": 32, "lucro_liquido": 20,
                         "ativo_total": 460, "patrimonio_liquido": 220}},
        ]
        r = compute_ttm(periods)
        assert r["status"] == "ok"
        # TTM revenue = sum of 4 quarters
        assert r["metrics"]["receita_liquida"] == 460  # 100+110+120+130
        assert r["metrics"]["ebitda"] == 115  # 25+28+30+32
        # TTM ativo_total = average of 4 (snapshot)
        assert r["metrics"]["ativo_total"] == (400+420+440+460) / 4
        # TTM ROE = TTM lucro / avg PL = (15+16+18+20) / ((200+210+215+220)/4)
        expected_roe = 69 / ((200+210+215+220) / 4)
        assert r["ratios"]["roe"] == pytest.approx(expected_roe, rel=1e-3)

    def test_ttm_missing_metric_is_none(self):
        from skills.cvm.financials.metrics import compute_ttm
        periods = [
            {"period": "1T", "year": 2024, "quarter": 1, "metrics": {"receita_liquida": 100}},
            {"period": "2T", "year": 2024, "quarter": 2, "metrics": {"receita_liquida": 110}},
            {"period": "3T", "year": 2024, "quarter": 3, "metrics": {"receita_liquida": 120}},
            {"period": "4T", "year": 2024, "quarter": 4, "metrics": {}},  # missing receita
        ]
        r = compute_ttm(periods)
        assert r["metrics"]["receita_liquida"] is None  # one quarter missing -> None


# ════════════════════════════════════════════════════════════════════════════
# DFC_MD (direct-method) D&A fallback chain
# ════════════════════════════════════════════════════════════════════════════

class TestDFCMDFallback:
    """v1.2 — D&A fallback for direct-method (DFC_MD) filers."""

    def test_da_indirect_method_primary(self):
        """D&A from DFC_MI (6.01.01.02) is the primary source."""
        from skills.cvm.financials.financials import _extract_metrics
        vals = {"6.01.01.02": 5000.0, "6.02.01.02": 3000.0}
        m = _extract_metrics(vals)
        assert m["da"] == 5000.0  # indirect method wins

    def test_da_direct_method_fallback(self):
        """When DFC_MI D&A is missing, fall back to DFC_MD (6.02.01.02)."""
        from skills.cvm.financials.financials import _extract_metrics
        vals = {"6.02.01.02": 3000.0}  # no 6.01.01.02
        m = _extract_metrics(vals)
        assert m["da"] == 3000.0  # direct method fallback

    def test_da_direct_method_alt_fallback(self):
        """Second fallback: 6.01.04 (DFC_MD alternative code)."""
        from skills.cvm.financials.financials import _extract_metrics
        vals = {"6.01.04": 2000.0}  # no 6.01.01.02, no 6.02.01.02
        m = _extract_metrics(vals)
        assert m["da"] == 2000.0

    def test_da_none_when_all_missing(self):
        from skills.cvm.financials.financials import _extract_metrics
        m = _extract_metrics({})
        assert m["da"] is None

    def test_ebitda_with_direct_method_da(self):
        """EBITDA = EBIT + D&A works with direct-method D&A."""
        from skills.cvm.financials.metrics import compute_ebitda
        ebitda, method = compute_ebitda(10000.0, 3000.0)
        assert ebitda == 13000.0
        assert method == "ebit+da"
