"""Tests for v1.9: EV/EBITDA metric + cash engine + da engine + ROIC update.

EV/EBITDA = (price × shares + debt - cash) / (EBIT + D&A)
Per-share value: EBITDA per share = (EBIT + D&A) / shares

This is the most complex metric: composes 6 engines.

Also tests:
- cash engine (BPA 1.01.01 snapshot)
- da engine (DFC description search, TTM)
- ROIC update (now subtracts cash from invested capital)
"""
from __future__ import annotations

import pytest
from skills.cvm.calculations.metrics import ev_ebitda as ev_metric
from skills.cvm.calculations.engines import cash as cash_engine
from skills.cvm.calculations.engines import da as da_engine


# ════════════════════════════════════════════════════════════════════════════
# EBITDA per share tests
# ════════════════════════════════════════════════════════════════════════════

class TestEbitdaPsAt:
    def test_basic_computation(self, monkeypatch):
        """ebitda_ps_at = (EBIT + D&A) / shares."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        # EBITDA = 70e9 + 15e9 = 85e9
        # EBITDA/share = 85e9 / 13e9 = 6.538...
        result = ev_metric.ebitda_ps_at("PETR4", "2024-06-30")
        assert result == pytest.approx(85e9 / 13e9, rel=1e-3)

    def test_missing_ebit(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        assert ev_metric.ebitda_ps_at("PETR4", "2024-06-30") is None

    def test_missing_da(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        assert ev_metric.ebitda_ps_at("PETR4", "2024-06-30") is None

    def test_negative_ebitda_returns_none(self, monkeypatch):
        """EBIT + D&A <= 0 -> EBITDA <= 0 -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        assert ev_metric.ebitda_ps_at("PETR4", "2024-06-30") is None


# ════════════════════════════════════════════════════════════════════════════
# EV/EBITDA ratio tests
# ════════════════════════════════════════════════════════════════════════════

class TestEvEbitdaAt:
    def test_basic_computation(self, monkeypatch):
        """ev_ebitda_at = (price × shares + debt - cash) / (EBIT + D&A)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        # EBITDA = 70e9 + 15e9 = 85e9
        # market_cap = 38.0 × 13e9 = 494e9
        # EV = 494e9 + 100e9 - 30e9 = 564e9
        # EV/EBITDA = 564e9 / 85e9 = 6.635...
        result = ev_metric.ev_ebitda_at("PETR4", "2024-06-30")
        assert result == pytest.approx(564e9 / 85e9, rel=1e-3)

    def test_missing_price(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        assert ev_metric.ev_ebitda_at("PETR4", "2024-06-30") is None

    def test_missing_debt(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.debt_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        assert ev_metric.ev_ebitda_at("PETR4", "2024-06-30") is None

    def test_missing_cash(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.cash_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        assert ev_metric.ev_ebitda_at("PETR4", "2024-06-30") is None

    def test_negative_ebitda_returns_none(self, monkeypatch):
        """Negative EBITDA -> EV/EBITDA meaningless -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_at", lambda c, d: 15e9)
        assert ev_metric.ev_ebitda_at("PETR4", "2024-06-30") is None


# ════════════════════════════════════════════════════════════════════════════
# EV/EBITDA history tests
# ════════════════════════════════════════════════════════════════════════════

class TestEvEbitdaHistory:
    def test_basic_shape(self, monkeypatch):
        """ev_ebitda_history should return series with both per-share + ratio + 6 engine components."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_ebitda.price_series",
            lambda t, df, dt: [{"date": "2024-01-15", "close": 38.0}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_ebitda.shares_periods",
            lambda c: [{"date": "2024-01-01", "shares": 13e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_ebitda.debt_periods",
            lambda c: [{"date": "2024-01-01", "debt": 100e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_ebitda.cash_periods",
            lambda c: [{"date": "2024-01-01", "cash": 30e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_ebitda.ebit_periods",
            lambda c: [{"date": "2024-01-01", "ttm_ebit": 70e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_ebitda.da_periods",
            lambda c: [{"date": "2024-01-01", "ttm_da": 15e9}],
        )
        result = ev_metric.ev_ebitda_history("PETR4", "2024-01-01", "2024-12-31")
        assert len(result) == 1
        entry = result[0]
        assert "date" in entry
        assert "price" in entry
        assert "ebitda_ps" in entry
        assert "ev_ebitda" in entry
        assert "ebit" in entry
        assert "da" in entry
        assert "debt" in entry
        assert "cash" in entry
        assert "shares" in entry
        # Verify computation
        assert entry["ebitda_ps"] == pytest.approx(85e9 / 13e9, rel=1e-3)
        assert entry["ev_ebitda"] == pytest.approx(564e9 / 85e9, rel=1e-3)

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.price_series", lambda t, df, dt: [])
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.shares_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.debt_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.cash_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.ebit_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_ebitda.da_periods", lambda c: [])
        assert ev_metric.ev_ebitda_history("PETR4", "2024-01-01", "2024-12-31") == []


# ════════════════════════════════════════════════════════════════════════════
# Registry tests
# ════════════════════════════════════════════════════════════════════════════

class TestEvEbitdaRegistry:
    def test_ev_ebitda_registered(self):
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["ev_ebitda"]
        assert spec.ratio_key == "ev_ebitda"
        assert spec.ratio_label == "EV/EBITDA"
        assert spec.per_share_key == "ebitda_ps"
        assert spec.per_share_label == "EBITDA/Ação"
        assert len(spec.engines) == 6

    def test_ev_ebitda_engines(self):
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["ev_ebitda"]
        for e in ["price", "shares", "debt", "cash", "ebit", "da"]:
            assert e in spec.engines

    def test_ev_ebitda_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("ev_ebit").name == "ev_ebitda"
        assert resolve_metric("evebitda").name == "ev_ebitda"


# ════════════════════════════════════════════════════════════════════════════
# Cash engine tests
# ════════════════════════════════════════════════════════════════════════════

class TestCashEngine:
    def test_cash_uses_codigo_1_01_01(self):
        assert cash_engine.CAIXA_CODE == "1.01.01"

    def test_cash_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "cash" in ENGINES
        assert ENGINES["cash"].category == "bpa"
        assert ENGINES["cash"].quantity == "cash"

    def test_cash_at_finds_most_recent_snapshot(self, monkeypatch):
        fake_dfp = {"2023-12-31": {"value": 30e9, "year": 2023}}
        fake_itr = {
            "2024-03-31": {"value": 35e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 40e9, "meses": 6, "year": 2024},
        }
        monkeypatch.setattr(cash_engine, "_get_dfp_cash", lambda c: fake_dfp)
        monkeypatch.setattr(cash_engine, "_get_itr_cash", lambda c: fake_itr)
        assert cash_engine.cash_at("PETR4", "2024-04-15") == 35e9
        assert cash_engine.cash_at("PETR4", "2024-07-01") == 40e9

    def test_cash_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(cash_engine, "_get_dfp_cash", lambda c: {})
        monkeypatch.setattr(cash_engine, "_get_itr_cash", lambda c: {})
        assert cash_engine.cash_at("PETR4", "2024-06-30") is None


# ════════════════════════════════════════════════════════════════════════════
# D&A engine tests
# ════════════════════════════════════════════════════════════════════════════

class TestDaEngine:
    def test_da_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "da" in ENGINES
        assert ENGINES["da"].category == "dfc"
        assert ENGINES["da"].quantity == "ttm_da"

    def test_da_at_ttm_derivation(self, monkeypatch):
        """da_at should derive TTM via DFP - ITR_prior + ITR_current."""
        fake_dfp = {"2023": {"value": 15e9, "date": "2023-12-31"}}
        fake_itr = {
            "2024-03-31": {"value": 4e9, "meses": 3, "year": 2024},
            "2023-03-31": {"value": 3e9, "meses": 3, "year": 2023},
        }
        monkeypatch.setattr(da_engine, "_get_dfp_da", lambda c: fake_dfp)
        monkeypatch.setattr(da_engine, "_get_itr_da", lambda c: fake_itr)
        # TTM = 15e9 - 3e9 + 4e9 = 16e9
        result = da_engine.da_at("PETR4", "2024-04-15")
        assert result == 16e9

    def test_da_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(da_engine, "_get_dfp_da", lambda c: {})
        monkeypatch.setattr(da_engine, "_get_itr_da", lambda c: {})
        assert da_engine.da_at("PETR4", "2024-06-30") is None

    def test_dfc_category_exists(self):
        from skills.cvm.calculations._registry import list_engine_categories
        cats = list_engine_categories()
        assert "dfc" in cats


# ════════════════════════════════════════════════════════════════════════════
# ROIC update tests (v1.9: now subtracts cash)
# ════════════════════════════════════════════════════════════════════════════

class TestRoicCashUpdate:
    def test_roic_subtracts_cash_when_available(self, monkeypatch):
        """v1.9: ROIC should subtract cash from invested capital.

        v2.1: roic_at now delegates to effective_tax_rate_at(). Mocked directly.
        """
        from skills.cvm.calculations.metrics import roic as roic_metric

        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.effective_tax_rate_at", lambda c, d: 15e9 / 90e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.debt_at", lambda c, d: 100e9)
        # Mock cash_at to return 50e9
        monkeypatch.setattr("skills.cvm.calculations.engines.cash.cash_at", lambda c, d: 50e9)
        # effective_tax_rate = 15e9 / 90e9 = 1/6
        # NOPAT = 70e9 × (1 - 1/6) = 70e9 × (5/6) = 58.333...e9
        # IC = 350e9 + 100e9 - 50e9 = 400e9 (v1.9: cash subtracted)
        # ROIC = 58.333...e9 / 400e9
        expected_nopat = 70e9 * (1 - 15e9 / 90e9)
        result = roic_metric.roic_at("PETR4", "2024-06-30")
        assert result == pytest.approx(expected_nopat / 400e9, rel=1e-3)

    def test_roic_falls_back_without_cash(self, monkeypatch):
        """If cash_at returns None (no data), ROIC falls back to PL + Debt.

        v2.1: roic_at now delegates to effective_tax_rate_at(). Mocked directly.
        """
        from skills.cvm.calculations.metrics import roic as roic_metric

        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.effective_tax_rate_at", lambda c, d: 15e9 / 90e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roic.debt_at", lambda c, d: 100e9)
        # Mock cash_at to return None
        monkeypatch.setattr("skills.cvm.calculations.engines.cash.cash_at", lambda c, d: None)
        # effective_tax_rate = 15e9 / 90e9 = 1/6
        # NOPAT = 70e9 × (5/6) = 58.333...e9
        # IC = 350e9 + 100e9 = 450e9 (fallback, no cash)
        # ROIC = 58.333...e9 / 450e9
        expected_nopat = 70e9 * (1 - 15e9 / 90e9)
        result = roic_metric.roic_at("PETR4", "2024-06-30")
        assert result == pytest.approx(expected_nopat / 450e9, rel=1e-3)

    def test_roic_engines_includes_cash(self):
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["roic"]
        assert "cash" in spec.engines
        # v2.0: ROIC now composes 6 engines (ebit + tax + ebt + pl + debt + cash)
        assert len(spec.engines) == 6
        assert "ebt" in spec.engines
