"""Tests for skills/cvm/financials/metrics.py.

Covers:
  - TestMetrics         : compute_ebitda + compute_ratios (annual / quarterly /
                          negative PL / None values) — 7 tests.
  - TestTTM             : compute_ttm (insufficient data / 4Q sums flows /
                          missing metric → None) — 4 tests.
  - TestDFCMDFallback   : _extract_metrics D&A fallback chain
                          (DFC_MI 6.01.01.02 → DFC_MD 6.02.01.02 →
                          None; 6.01.04 is FX variation, not D&A) +
                          variacao_cambial key + EBITDA with direct-method
                          D&A — 6 tests.

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
        from skills.cvm.financials.fetchers import _extract_metrics
        vals = {"6.01.01.02": 5000.0, "6.02.01.02": 3000.0}
        m = _extract_metrics(vals)
        assert m["da"] == 5000.0  # indirect method wins

    def test_da_direct_method_fallback(self):
        """When DFC_MI D&A is missing, fall back to DFC_MD (6.02.01.02)."""
        from skills.cvm.financials.fetchers import _extract_metrics
        vals = {"6.02.01.02": 3000.0}  # no 6.01.01.02
        m = _extract_metrics(vals)
        assert m["da"] == 3000.0  # direct method fallback

    def test_da_direct_method_alt_fallback(self):
        """[v1.5 fix-tests-version] 6.01.04 is NO LONGER a D&A fallback.

        The 6.01.04 code is "Variações Cambiais" (foreign exchange variations)
        under DFC operating cash flow — it is NOT depreciation & amortization.
        Using it as a D&A fallback incorrectly inflated EBITDA for filers that
        reported FX variations but no D&A in their indirect-method DFC.
        The 6.01.04 value is now exposed as the dedicated `variacao_cambial`
        key (see test_variacao_cambial_key below).
        """
        from skills.cvm.financials.fetchers import _extract_metrics
        vals = {"6.01.04": 2000.0}  # no 6.01.01.02, no 6.02.01.02
        m = _extract_metrics(vals)
        assert m["da"] is None  # FX variation is not D&A
        # The value surfaces on the variacao_cambial key instead.
        assert m["variacao_cambial"] == 2000.0

    def test_variacao_cambial_key(self):
        """[v1.5 fix-tests-version] _extract_metrics exposes a
        `variacao_cambial` key sourced from DFC code 6.01.04.

        This is the same code that used to (incorrectly) be a D&A fallback.
        The key is always present (None when 6.01.04 is missing) so consumers
        can render the FX variation row on the DFC statement independently
        from D&A.
        """
        from skills.cvm.financials.fetchers import _extract_metrics
        # When 6.01.04 is present, variacao_cambial carries its value.
        m = _extract_metrics({"6.01.04": 2000.0})
        assert m["variacao_cambial"] == 2000.0
        # When 6.01.04 is absent, variacao_cambial is None (not a KeyError).
        m2 = _extract_metrics({"6.01.01.02": 5000.0})
        assert m2["variacao_cambial"] is None
        # And it's always in the returned dict.
        assert "variacao_cambial" in _extract_metrics({})

    def test_da_none_when_all_missing(self):
        from skills.cvm.financials.fetchers import _extract_metrics
        m = _extract_metrics({})
        assert m["da"] is None

    def test_ebitda_with_direct_method_da(self):
        """EBITDA = EBIT + D&A works with direct-method D&A."""
        from skills.cvm.financials.metrics import compute_ebitda
        ebitda, method = compute_ebitda(10000.0, 3000.0)
        assert ebitda == 13000.0
        assert method == "ebit+da"


# ════════════════════════════════════════════════════════════════════════════
# v1.3 — Engine-backed variants (compute_ebitda_from_engines, compute_ttm_with_engines)
# ════════════════════════════════════════════════════════════════════════════

class TestEngineBackedVariants:
    """[v1.3 migration / v1.4 top-level imports] Engine-backed variants that
    delegate TTM flows to skills.cvm.calculations engines instead of summing
    4 standalone quarters.

    [v1.4] The engines are now imported at the TOP of metrics.py, so we patch
    them on the metrics module's namespace (`skills.cvm.financials.metrics.<fn>`)
    rather than on the source engine modules. This is the pattern documented in
    the task brief and matches how the v1.4-valuation skill tests mock their
    calculations metric imports.

    These tests verify that compute_ebitda_from_engines / compute_ttm_with_engines
    correctly compose the engines and apply the ebit_only fallback — the engines
    themselves are NOT invoked.
    """

    def test_compute_ebitda_from_engines_both_available(self, monkeypatch):
        """Both ebit_at + da_at return values → 'ebit+da'."""
        from skills.cvm.financials import metrics as M

        monkeypatch.setattr(M, "ebit_at", lambda c, d: 20_000_000)
        monkeypatch.setattr(M, "da_at", lambda c, d: 3_000_000)

        ebitda, method = M.compute_ebitda_from_engines("TEST", "2024-12-31")
        assert ebitda == 23_000_000
        assert method == "ebit+da"

    def test_compute_ebitda_from_engines_da_missing(self, monkeypatch):
        """da_at returns None → 'ebit_only' (EBITDA = EBIT)."""
        from skills.cvm.financials import metrics as M

        monkeypatch.setattr(M, "ebit_at", lambda c, d: 20_000_000)
        monkeypatch.setattr(M, "da_at", lambda c, d: None)

        ebitda, method = M.compute_ebitda_from_engines("TEST", "2024-12-31")
        assert ebitda == 20_000_000
        assert method == "ebit_only"

    def test_compute_ebitda_from_engines_ebit_missing(self, monkeypatch):
        """ebit_at returns None → 'none'."""
        from skills.cvm.financials import metrics as M

        monkeypatch.setattr(M, "ebit_at", lambda c, d: None)
        monkeypatch.setattr(M, "da_at", lambda c, d: 3_000_000)

        ebitda, method = M.compute_ebitda_from_engines("TEST", "2024-12-31")
        assert ebitda is None
        assert method == "none"

    def test_compute_ebitda_from_engines_engine_error_swallowed(self, monkeypatch):
        """Engine raises FileNotFoundError → _safe_engine_call returns None
        → 'none' (graceful degradation when DFC DB is not synced)."""
        from skills.cvm.financials import metrics as M

        def _raise(*a, **k):
            raise FileNotFoundError("dfp.db not synced")

        monkeypatch.setattr(M, "ebit_at", _raise)

        ebitda, method = M.compute_ebitda_from_engines("TEST", "2024-12-31")
        assert ebitda is None
        assert method == "none"

    def test_compute_ttm_with_engines_uses_engines_for_flows(self, monkeypatch):
        """Flow metrics come from calculations engines; snapshots averaged
        from the 4 periods list (engine returns single point, different
        semantics)."""
        from skills.cvm.financials import metrics as M

        monkeypatch.setattr(M, "revenue_at",       lambda c, d: 500_000_000)
        monkeypatch.setattr(M, "ebit_at",          lambda c, d: 200_000_000)
        monkeypatch.setattr(M, "da_at",            lambda c, d: 30_000_000)
        monkeypatch.setattr(M, "ttm_earnings_at",  lambda c, d: 120_000_000)
        monkeypatch.setattr(M, "operating_cf_at",  lambda c, d: 180_000_000)
        monkeypatch.setattr(M, "investing_cf_at",  lambda c, d: -80_000_000)
        monkeypatch.setattr(M, "financing_cf_at",  lambda c, d: -50_000_000)

        periods = [
            {"period": "1T2024", "year": 2024, "quarter": 1,
             "metrics": {"ativo_total": 400, "caixa": 100,
                         "patrimonio_liquido": 200, "divida_bruta": 150},
             "ratios": {}},
            {"period": "2T2024", "year": 2024, "quarter": 2,
             "metrics": {"ativo_total": 420, "caixa": 110,
                         "patrimonio_liquido": 210, "divida_bruta": 160},
             "ratios": {}},
            {"period": "3T2024", "year": 2024, "quarter": 3,
             "metrics": {"ativo_total": 440, "caixa": 120,
                         "patrimonio_liquido": 215, "divida_bruta": 170},
             "ratios": {}},
            {"period": "4T2024", "year": 2024, "quarter": 4,
             "metrics": {"ativo_total": 460, "caixa": 130,
                         "patrimonio_liquido": 220, "divida_bruta": 180},
             "ratios": {}},
        ]
        r = M.compute_ttm_with_engines("TEST", "2024-12-31", periods)
        assert r["status"] == "ok"

        # Flow metrics from engines (single TTM value, not sum of 4)
        assert r["metrics"]["receita_liquida"] == 500_000_000
        assert r["metrics"]["ebit"] == 200_000_000
        assert r["metrics"]["da"] == 30_000_000
        assert r["metrics"]["ebitda"] == 230_000_000  # 200M + 30M
        assert r["metrics"]["ebitda_method"] == "ebit+da"
        assert r["metrics"]["lucro_liquido"] == 120_000_000
        assert r["metrics"]["fco"] == 180_000_000
        assert r["metrics"]["fci"] == -80_000_000
        assert r["metrics"]["fcf"] == -50_000_000

        # Snapshot metrics averaged from the 4 periods (NOT from engines)
        assert r["metrics"]["ativo_total"] == (400 + 420 + 440 + 460) / 4
        assert r["metrics"]["caixa"] == (100 + 110 + 120 + 130) / 4
        assert r["metrics"]["patrimonio_liquido"] == (200 + 210 + 215 + 220) / 4
        assert r["metrics"]["divida_bruta"] == (150 + 160 + 170 + 180) / 4

    def test_compute_ttm_with_engines_insufficient_periods(self):
        """Fewer than 4 periods → 'insufficient_data' (no engine calls)."""
        from skills.cvm.financials.metrics import compute_ttm_with_engines
        r = compute_ttm_with_engines("TEST", "2024-12-31", [])
        assert r["status"] == "insufficient_data"

    def test_compute_ttm_with_engines_ebit_only_fallback(self, monkeypatch):
        """When da_at returns None, ebitda_method = 'ebit_only' (EBITDA = EBIT)."""
        from skills.cvm.financials import metrics as M

        monkeypatch.setattr(M, "revenue_at",       lambda c, d: 500_000_000)
        monkeypatch.setattr(M, "ebit_at",          lambda c, d: 200_000_000)
        monkeypatch.setattr(M, "da_at",            lambda c, d: None)  # D&A missing
        monkeypatch.setattr(M, "ttm_earnings_at",  lambda c, d: 120_000_000)
        monkeypatch.setattr(M, "operating_cf_at",  lambda c, d: 180_000_000)
        monkeypatch.setattr(M, "investing_cf_at",  lambda c, d: -80_000_000)
        monkeypatch.setattr(M, "financing_cf_at",  lambda c, d: -50_000_000)

        periods = [
            {"period": f"Q{i}T2024", "year": 2024, "quarter": i,
             "metrics": {"ativo_total": 400, "patrimonio_liquido": 200,
                         "caixa": 100, "divida_bruta": 150}, "ratios": {}}
            for i in (1, 2, 3, 4)
        ]
        r = M.compute_ttm_with_engines("TEST", "2024-12-31", periods)
        assert r["status"] == "ok"
        assert r["metrics"]["ebitda"] == 200_000_000  # EBIT only
        assert r["metrics"]["ebitda_method"] == "ebit_only"
