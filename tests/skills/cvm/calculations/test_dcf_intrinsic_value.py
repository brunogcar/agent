"""Tests for DCF Intrinsic Value + Margin of Safety.

Mocks all inputs (FCF, WACC, shares, price, growth, IPCA).
"""
from __future__ import annotations
import pytest


@pytest.fixture
def mock_dcf_inputs(monkeypatch):
    """Mock all inputs DCF depends on."""
    # FCF: FCO=280e9, FCI=-100e9 → FCF=180e9
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.operating_cf_at",
        lambda c, d: 280e9,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.investing_cf_at",
        lambda c, d: -100e9,
    )
    # WACC = 12%
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.wacc_at",
        lambda c, d: 0.12,
    )
    # Shares = 13 billion
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.shares_at",
        lambda c, d: 13e9,
    )
    # Price = 38.00 BRL
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.price_at",
        lambda c, d: 38.0,
    )
    # Revenue growth 1Y = 10%
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.revenue_growth_1y_at",
        lambda c, d: 0.10,
    )
    # IPCA terminal growth = 5% (mock get_terminal_growth)
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dcf_intrinsic_value.get_terminal_growth",
        lambda: 0.05,
    )


class TestDcfIntrinsicValue:
    def test_basic_computation(self, mock_dcf_inputs):
        """DCF should return a positive intrinsic value per share."""
        from skills.cvm.calculations.metrics.dcf_intrinsic_value import dcf_intrinsic_value_at
        result = dcf_intrinsic_value_at("PETR4", "2024-06-30")
        assert result is not None
        assert result > 0
        # FCF=180e9, shares=13e9 → FCF/share ≈ 13.85
        # With 10% growth, 12% WACC, 5% terminal, should be > price (38.0)

    def test_none_fco_returns_none(self, monkeypatch):
        """Missing FCO → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.operating_cf_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.wacc_at",
            lambda c, d: 0.12,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.shares_at",
            lambda c, d: 13e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.revenue_growth_1y_at",
            lambda c, d: 0.10,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.get_terminal_growth",
            lambda: 0.05,
        )
        from skills.cvm.calculations.metrics.dcf_intrinsic_value import dcf_intrinsic_value_at
        assert dcf_intrinsic_value_at("PETR4", "2024-06-30") is None

    def test_negative_fcf_returns_none(self, monkeypatch):
        """FCF <= 0 → None (can't project from negative FCF)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.operating_cf_at",
            lambda c, d: 50e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.investing_cf_at",
            lambda c, d: -100e9,  # FCF = -50e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.wacc_at",
            lambda c, d: 0.12,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.shares_at",
            lambda c, d: 13e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.revenue_growth_1y_at",
            lambda c, d: 0.10,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.get_terminal_growth",
            lambda: 0.05,
        )
        from skills.cvm.calculations.metrics.dcf_intrinsic_value import dcf_intrinsic_value_at
        assert dcf_intrinsic_value_at("PETR4", "2024-06-30") is None

    def test_wacc_le_terminal_growth_returns_none(self, monkeypatch):
        """WACC <= terminal growth → terminal value undefined → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.wacc_at",
            lambda c, d: 0.04,  # WACC = 4%
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.shares_at",
            lambda c, d: 13e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.revenue_growth_1y_at",
            lambda c, d: 0.10,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dcf_intrinsic_value.get_terminal_growth",
            lambda: 0.05,  # Terminal = 5% > WACC = 4%
        )
        from skills.cvm.calculations.metrics.dcf_intrinsic_value import dcf_intrinsic_value_at
        assert dcf_intrinsic_value_at("PETR4", "2024-06-30") is None

    def test_margin_of_safety(self, mock_dcf_inputs):
        """Margin of Safety = (intrinsic - price) / intrinsic."""
        from skills.cvm.calculations.metrics.dcf_intrinsic_value import (
            dcf_intrinsic_value_at, dcf_margin_of_safety_at,
        )
        intrinsic = dcf_intrinsic_value_at("PETR4", "2024-06-30")
        mos = dcf_margin_of_safety_at("PETR4", "2024-06-30")
        assert mos is not None
        assert -1.0 <= mos <= 1.0
        # Verify: mos = (intrinsic - 38.0) / intrinsic
        expected_mos = (intrinsic - 38.0) / intrinsic
        assert mos == pytest.approx(expected_mos, rel=1e-6)

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert "dcf_intrinsic_value" in METRICS
        assert "dcf_margin_of_safety" in METRICS
        assert resolve_metric("dcf").name == "dcf_intrinsic_value"
        assert resolve_metric("valor_intrinseco").name == "dcf_intrinsic_value"
