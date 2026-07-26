"""Tests for v1.8: ROIC metric + tax engine + debt engine.

ROIC = NOPAT / Invested Capital
NOPAT = EBIT - max(0, tax_expense)
Invested Capital = PL + Debt

Tests mirror test_roe.py structure (fundamental ratio pattern) + test the
two new engines (tax = TTM, debt = snapshot summing 2 codes).
"""
from __future__ import annotations

import pytest
from skills.cvm.historical.metrics import roic as roic_metric
from skills.cvm.historical.engines import tax as tax_engine
from skills.cvm.historical.engines import debt as debt_engine


# ════════════════════════════════════════════════════════════════════════════
# ROIC metric tests
# ════════════════════════════════════════════════════════════════════════════

class TestRoicAt:
    def test_basic_computation(self, monkeypatch):
        """roic_at = NOPAT / (PL + Debt) = (EBIT - tax_expense) / (PL + Debt)."""
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: -15e9)  # negative = expense
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        # NOPAT = 70e9 - 15e9 = 55e9
        # IC = 350e9 + 100e9 = 450e9
        # ROIC = 55e9 / 450e9 = 0.1222...
        result = roic_metric.roic_at("PETR4", "2024-06-30")
        assert result == pytest.approx(55e9 / 450e9, rel=1e-3)

    def test_zero_tax(self, monkeypatch):
        """If tax is 0 or None, NOPAT = EBIT."""
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        # NOPAT = 70e9 - 0 = 70e9
        # ROIC = 70e9 / 450e9
        result = roic_metric.roic_at("PETR4", "2024-06-30")
        assert result == pytest.approx(70e9 / 450e9, rel=1e-3)

    def test_positive_tax_is_treated_as_zero_expense(self, monkeypatch):
        """If tax is positive (tax credit), tax_expense = 0."""
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: 5e9)  # positive = credit
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        # NOPAT = 70e9 - 0 = 70e9 (tax credit doesn't increase NOPAT)
        result = roic_metric.roic_at("PETR4", "2024-06-30")
        assert result == pytest.approx(70e9 / 450e9, rel=1e-3)

    def test_negative_ebit_returns_none(self, monkeypatch):
        """Operating losses -> ROIC meaningless -> None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: -5e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        assert roic_metric.roic_at("PETR4", "2024-06-30") is None

    def test_missing_ebit(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: -15e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        assert roic_metric.roic_at("PETR4", "2024-06-30") is None

    def test_missing_pl(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: -15e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        assert roic_metric.roic_at("PETR4", "2024-06-30") is None

    def test_missing_debt(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: -15e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: None)
        assert roic_metric.roic_at("PETR4", "2024-06-30") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity -> ROIC meaningless -> None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_at", lambda c, d: -15e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_at", lambda c, d: 100e9)
        assert roic_metric.roic_at("PETR4", "2024-06-30") is None


class TestRoicHistory:
    def test_basic_shape(self, monkeypatch):
        """roic_history should return series with roic + 4 engine components (no price/shares)."""
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.roic.ebit_periods",
            lambda c: [{"date": "2024-03-31", "ttm_ebit": 70e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.roic.tax_periods",
            lambda c: [{"date": "2024-03-31", "ttm_tax": -15e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.roic.pl_periods",
            lambda c: [{"date": "2024-03-31", "pl": 350e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.roic.debt_periods",
            lambda c: [{"date": "2024-03-31", "debt": 100e9}],
        )
        result = roic_metric.roic_history("PETR4", "2024-01-01", "2024-12-31")
        assert len(result) >= 1
        for entry in result:
            assert "date" in entry
            assert "roic" in entry
            assert "ttm_ebit" in entry
            assert "ttm_tax" in entry
            assert "pl" in entry
            assert "debt" in entry
            assert "price" not in entry
            assert "shares" not in entry

    def test_empty_periods_returns_empty(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.ebit_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.tax_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.pl_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.historical.metrics.roic.debt_periods", lambda c: [])
        assert roic_metric.roic_history("PETR4", "2024-01-01", "2024-12-31") == []


class TestRoicRegistry:
    def test_roic_registered(self):
        from skills.cvm.historical._registry import METRICS
        spec = METRICS["roic"]
        assert spec.ratio_key == "roic"
        assert spec.ratio_label == "ROIC"
        assert spec.per_share_key is None
        assert "ebit" in spec.engines
        assert "tax" in spec.engines
        assert "pl" in spec.engines
        assert "debt" in spec.engines

    def test_roic_aliases(self):
        from skills.cvm.historical._registry import resolve_metric
        assert resolve_metric("return_on_invested_capital").name == "roic"
        assert resolve_metric("retorno_capital_investido").name == "roic"


# ════════════════════════════════════════════════════════════════════════════
# Tax engine tests
# ════════════════════════════════════════════════════════════════════════════

class TestTaxEngine:
    def test_tax_uses_codigo_3_08(self):
        """Tax engine should query DRE codigo 3.08."""
        assert tax_engine.INCOME_TAX_CODE == "3.08"

    def test_tax_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "tax" in ENGINES
        assert ENGINES["tax"].category == "dre"
        assert ENGINES["tax"].quantity == "ttm_tax"

    def test_tax_at_ttm_derivation(self, monkeypatch):
        """tax_at should derive TTM via DFP - ITR_prior + ITR_current."""
        fake_dfp = {"2023": {"value": -30e9, "date": "2023-12-31"}}
        fake_itr = {
            "2024-03-31": {"value": -7e9, "meses": 3, "year": 2024},
            "2023-03-31": {"value": -6e9, "meses": 3, "year": 2023},
        }
        monkeypatch.setattr(tax_engine, "_get_dfp_tax", lambda c: fake_dfp)
        monkeypatch.setattr(tax_engine, "_get_itr_tax", lambda c: fake_itr)
        # TTM = -30e9 - (-6e9) + (-7e9) = -30e9 + 6e9 - 7e9 = -31e9
        result = tax_engine.tax_at("PETR4", "2024-04-15")
        assert result == -31e9

    def test_tax_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(tax_engine, "_get_dfp_tax", lambda c: {})
        monkeypatch.setattr(tax_engine, "_get_itr_tax", lambda c: {})
        assert tax_engine.tax_at("PETR4", "2024-06-30") is None

    def test_tax_periods_builds_step_function(self, monkeypatch):
        fake_dfp = {"2023": {"value": -30e9, "date": "2023-12-31"}}
        fake_itr = {
            "2024-03-31": {"value": -7e9, "meses": 3, "year": 2024},
            "2023-03-31": {"value": -6e9, "meses": 3, "year": 2023},
        }
        monkeypatch.setattr(tax_engine, "_get_dfp_tax", lambda c: fake_dfp)
        monkeypatch.setattr(tax_engine, "_get_itr_tax", lambda c: fake_itr)
        result = tax_engine.tax_periods("PETR4")
        assert len(result) >= 1
        for p in result:
            assert "date" in p
            assert "ttm_tax" in p


# ════════════════════════════════════════════════════════════════════════════
# Debt engine tests
# ════════════════════════════════════════════════════════════════════════════

class TestDebtEngine:
    def test_debt_uses_codes_2_01_04_and_2_02_01(self):
        """Debt engine should query BPP codigos 2.01.04 + 2.02.01."""
        assert "2.01.04" in debt_engine.DEBT_CODES
        assert "2.02.01" in debt_engine.DEBT_CODES
        assert len(debt_engine.DEBT_CODES) == 2

    def test_debt_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "debt" in ENGINES
        assert ENGINES["debt"].category == "bpp"
        assert ENGINES["debt"].quantity == "debt"

    def test_debt_at_finds_most_recent_snapshot(self, monkeypatch):
        """debt_at should return the most recent debt snapshot <= date."""
        fake_dfp = {"2023-12-31": {"value": 200e9, "year": 2023}}
        fake_itr = {
            "2024-03-31": {"value": 210e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 220e9, "meses": 6, "year": 2024},
        }
        monkeypatch.setattr(debt_engine, "_get_dfp_debt", lambda c: fake_dfp)
        monkeypatch.setattr(debt_engine, "_get_itr_debt", lambda c: fake_itr)
        assert debt_engine.debt_at("PETR4", "2024-04-15") == 210e9
        assert debt_engine.debt_at("PETR4", "2024-07-01") == 220e9
        assert debt_engine.debt_at("PETR4", "2023-12-31") == 200e9

    def test_debt_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(debt_engine, "_get_dfp_debt", lambda c: {})
        monkeypatch.setattr(debt_engine, "_get_itr_debt", lambda c: {})
        assert debt_engine.debt_at("PETR4", "2024-06-30") is None

    def test_debt_periods_merges_dfp_and_itr(self, monkeypatch):
        fake_dfp = {
            "2023-12-31": {"value": 200e9, "year": 2023},
            "2024-12-31": {"value": 250e9, "year": 2024},
        }
        fake_itr = {
            "2024-03-31": {"value": 210e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 220e9, "meses": 6, "year": 2024},
        }
        monkeypatch.setattr(debt_engine, "_get_dfp_debt", lambda c: fake_dfp)
        monkeypatch.setattr(debt_engine, "_get_itr_debt", lambda c: fake_itr)
        result = debt_engine.debt_periods("PETR4")
        assert len(result) == 4  # 2 DFP + 2 ITR
        assert result[0] == {"date": "2023-12-31", "debt": 200e9}
        assert result[-1] == {"date": "2024-12-31", "debt": 250e9}
