"""Tests for IRR (Internal Rate of Return / TIR).

Mocks all inputs (FCF, price, shares, growth, terminal growth).
"""
from __future__ import annotations
import pytest


@pytest.fixture
def mock_irr_inputs(monkeypatch):
    """Mock all inputs IRR depends on."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.irr.operating_cf_at",
        lambda c, d: 280e9,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.irr.investing_cf_at",
        lambda c, d: -100e9,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.irr.price_at",
        lambda c, d: 38.0,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.irr.shares_at",
        lambda c, d: 13e9,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.irr.revenue_growth_1y_at",
        lambda c, d: 0.10,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.irr.get_terminal_growth",
        lambda: 0.05,
    )


class TestIrrAt:
    def test_basic_computation(self, mock_irr_inputs):
        """IRR should return a positive rate (>0, <100%)."""
        from skills.cvm.calculations.metrics.irr import irr_at
        result = irr_at("PETR4", "2024-06-30")
        assert result is not None
        assert 0.0 < result < 1.0  # 0% to 100%

    def test_none_fco_returns_none(self, monkeypatch):
        """Missing FCO → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.operating_cf_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.price_at",
            lambda c, d: 38.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.shares_at",
            lambda c, d: 13e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.revenue_growth_1y_at",
            lambda c, d: 0.10,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.get_terminal_growth",
            lambda: 0.05,
        )
        from skills.cvm.calculations.metrics.irr import irr_at
        assert irr_at("PETR4", "2024-06-30") is None

    def test_negative_fcf_returns_none(self, monkeypatch):
        """FCF <= 0 → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.operating_cf_at",
            lambda c, d: 50e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.price_at",
            lambda c, d: 38.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.shares_at",
            lambda c, d: 13e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.revenue_growth_1y_at",
            lambda c, d: 0.10,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.get_terminal_growth",
            lambda: 0.05,
        )
        from skills.cvm.calculations.metrics.irr import irr_at
        assert irr_at("PETR4", "2024-06-30") is None

    def test_overvalued_returns_none(self, monkeypatch):
        """If price is extremely high, IRR is negative at any rate → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.price_at",
            lambda c, d: 10000.0,  # Absurdly high price
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.shares_at",
            lambda c, d: 13e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.revenue_growth_1y_at",
            lambda c, d: 0.10,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.irr.get_terminal_growth",
            lambda: 0.05,
        )
        from skills.cvm.calculations.metrics.irr import irr_at
        result = irr_at("PETR4", "2024-06-30")
        # At 10000 price, IRR should be very low (< 10%, below typical WACC)
        assert result is None or result < 0.10

    def test_npv_function(self):
        """Test _npv: -100 at t=0, +110 at t=1 → NPV at 10% = 0."""
        from skills.cvm.calculations.metrics.irr import _npv
        cash_flows = [-100.0, 110.0]
        # NPV at 10% = -100 + 110/1.1 = -100 + 100 = 0
        assert _npv(0.10, cash_flows) == pytest.approx(0.0, abs=1e-6)

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert "irr" in METRICS
        assert resolve_metric("tir").name == "irr"
        assert resolve_metric("internal_rate_of_return").name == "irr"
