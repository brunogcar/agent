"""Tests for skills/cvm/calculations/metrics/wacc.py.

[v2.0]

WACC = COE × (E / (D + E)) + Kd × (1 - tax) × (D / (D + E))

Mocks the underlying engines + composed metrics (coe, effective_tax_rate,
price, shares, debt, interest_paid, financial_result) — no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import wacc as wacc_metric


# ── Mock helpers ─────────────────────────────────────────────────────────────

def _mock_wacc_inputs(
    monkeypatch,
    *,
    coe: float | None = 0.166,           # 16.6% (CAPM cost of equity)
    price: float | None = 38.0,          # BRL
    shares: float | None = 13e9,         # 13 billion shares
    debt: float | None = 250e9,          # BRL 250B
    interest_paid: float | None = -8e9,  # BRL 8B outflow (DVA reports negative)
    financial_result: float | None = -7e9,
    tax: float | None = 0.25,            # 25% effective tax rate
    selic: float | None = 10.0,          # 10% annualized Selic (for fallbacks)
):
    """Mock all inputs WACC depends on (including selic_at for fallbacks)."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.coe_at",
        lambda c, d: coe,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.price_at",
        lambda c, d: price,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.shares_at",
        lambda c, d: shares,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.debt_at",
        lambda c, d: debt,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.interest_paid_at",
        lambda c, d: interest_paid,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.financial_result_at",
        lambda c, d: financial_result,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.effective_tax_rate_at",
        lambda c, d: tax,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.wacc.selic_at",
        lambda c, d: selic,
    )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestWaccAt:
    def test_basic_computation(self, monkeypatch):
        """WACC = COE × E/(D+E) + Kd × (1-tax) × D/(D+E).

        Default mocks:
          E = 38 × 13e9 = 494e9
          D = 250e9
          D+E = 744e9
          Kd = |−8e9| / 250e9 = 0.032
          tax = 0.25
          COE = 0.166
          WACC = 0.166 × (494/744) + 0.032 × 0.75 × (250/744)
               = 0.110241... + 0.0080645...
               = 0.118306...
        """
        _mock_wacc_inputs(monkeypatch)
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        assert result is not None

        e = 38.0 * 13e9
        d = 250e9
        v = d + e
        kd = abs(-8e9) / d
        expected = 0.166 * (e / v) + kd * (1 - 0.25) * (d / v)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_all_equity_firm_returns_coe(self, monkeypatch):
        """When debt = 0, WACC collapses to COE (debt weight = 0)."""
        _mock_wacc_inputs(monkeypatch, debt=0.0, interest_paid=0.0)
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        # WACC = COE × 1 + Kd × ... × 0 = COE
        assert result is not None
        assert result == pytest.approx(0.166, rel=1e-6)

    def test_none_coe_uses_selic_fallback(self, monkeypatch):
        """[v4] COE = None → falls back to Selic + ERP (Beta=1.0)."""
        _mock_wacc_inputs(monkeypatch, coe=None, selic=10.0)
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        assert result is not None
        # COE fallback = 10% + 5.5% = 15.5% = 0.155
        e = 38.0 * 13e9
        d = 250e9
        v = d + e
        kd = abs(-8e9) / d
        coe_fallback = 0.155
        expected = coe_fallback * (e / v) + kd * (1 - 0.25) * (d / v)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_none_coe_and_none_selic_returns_none(self, monkeypatch):
        """[v4] COE = None AND Selic = None → can't compute → None."""
        _mock_wacc_inputs(monkeypatch, coe=None, selic=None)
        assert wacc_metric.wacc_at("PETR4", "2024-06-30") is None

    def test_none_price_returns_none(self, monkeypatch):
        """Missing market price → can't compute market cap → None."""
        _mock_wacc_inputs(monkeypatch, price=None)
        assert wacc_metric.wacc_at("PETR4", "2024-06-30") is None

    def test_none_shares_returns_none(self, monkeypatch):
        """Missing shares outstanding → can't compute market cap → None."""
        _mock_wacc_inputs(monkeypatch, shares=None)
        assert wacc_metric.wacc_at("PETR4", "2024-06-30") is None

    def test_none_debt_returns_none(self, monkeypatch):
        """Missing debt snapshot → treat as missing data → None."""
        _mock_wacc_inputs(monkeypatch, debt=None)
        assert wacc_metric.wacc_at("PETR4", "2024-06-30") is None

    def test_none_interest_paid_falls_back_to_financial_result(self, monkeypatch):
        """When interest_paid is None but financial_result is available,
        Kd = |financial_result| / debt."""
        _mock_wacc_inputs(
            monkeypatch,
            interest_paid=None,
            financial_result=-10e9,  # 10B net financial expense
        )
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        assert result is not None

        e = 38.0 * 13e9
        d = 250e9
        v = d + e
        kd = abs(-10e9) / d  # = 0.04
        expected = 0.166 * (e / v) + kd * (1 - 0.25) * (d / v)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_none_interest_paid_and_none_financial_result_uses_default_kd(
        self, monkeypatch
    ):
        """[v3] When both interest_paid AND financial_result are None and debt > 0,
        Kd falls back to Selic + 3% credit spread (was returning None)."""
        _mock_wacc_inputs(
            monkeypatch,
            interest_paid=None,
            financial_result=None,
            selic=10.0,  # selic_at now in _mock_wacc_inputs
        )
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        assert result is not None
        # Kd = (10% + 3%) / 100 = 0.13
        e = 38.0 * 13e9
        d = 250e9
        v = d + e
        kd = 0.13
        expected = 0.166 * (e / v) + kd * (1 - 0.25) * (d / v)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_none_tax_uses_default_25_pct(self, monkeypatch):
        """When effective_tax_rate is None, default to 0.25 (Brazil IRPJ+CSLL)."""
        _mock_wacc_inputs(monkeypatch, tax=None)
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        assert result is not None

        e = 38.0 * 13e9
        d = 250e9
        v = d + e
        kd = abs(-8e9) / d
        # tax = 0.25 (default), not None
        expected = 0.166 * (e / v) + kd * (1 - 0.25) * (d / v)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_positive_interest_paid_treated_as_absolute(self, monkeypatch):
        """Even if interest_paid is (unusually) positive, Kd should be positive."""
        _mock_wacc_inputs(monkeypatch, interest_paid=8e9)
        result = wacc_metric.wacc_at("PETR4", "2024-06-30")
        assert result is not None

        e = 38.0 * 13e9
        d = 250e9
        v = d + e
        kd = 8e9 / d  # abs() of positive is the same
        expected = 0.166 * (e / v) + kd * (1 - 0.25) * (d / v)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_zero_price_returns_none(self, monkeypatch):
        """Zero price → market cap = 0 (degenerate) → None."""
        _mock_wacc_inputs(monkeypatch, price=0.0)
        assert wacc_metric.wacc_at("PETR4", "2024-06-30") is None


class TestWaccRegistry:
    def test_wacc_registered(self):
        """Verify wacc is registered in the metric registry."""
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert "wacc" in METRICS
        spec = METRICS["wacc"]
        assert spec.ratio_key == "wacc"
        assert spec.ratio_label == "WACC"
        assert spec.per_share_key is None
        assert spec.per_share_fn is None
        assert spec.category == "valuation"
        assert spec.allow_negative is False
        assert resolve_metric("wacc").name == "wacc"

    def test_wacc_engines(self):
        """Verify WACC lists all composed engines."""
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["wacc"]
        # Must include the primary engines
        assert "coe" in spec.engines
        assert "price" in spec.engines
        assert "shares" in spec.engines
        assert "debt" in spec.engines
        assert "interest_paid" in spec.engines
        # Fallback Kd engine
        assert "financial_result" in spec.engines

    def test_wacc_tooltip(self):
        """Verify the tooltip is set (PT-BR formula + DCF note)."""
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["wacc"]
        assert spec.tooltip is not None
        assert "WACC" in spec.tooltip
        assert "DCF" in spec.tooltip

    def test_wacc_aliases(self):
        """Verify the aliases resolve correctly."""
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("weighted_average_cost_of_capital").name == "wacc"
        assert resolve_metric("custo_medio_capital").name == "wacc"
