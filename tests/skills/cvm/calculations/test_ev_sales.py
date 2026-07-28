"""Tests for EV/Sales = (price × shares + debt - cash) / Revenue.

Type 2 fundamental valuation ratio. Guards: revenue <= 0 -> None, EV <= 0 -> None.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import ev_sales as ev_sales_metric


class TestEvSalesAt:
    def test_basic_computation(self, monkeypatch):
        """ev_sales_at = (price×shares + debt - cash) / revenue."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.cash_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.revenue_at", lambda c, d: 350e9)
        # EV = 38.0 × 13e9 + 200e9 - 80e9 = 494e9 + 200e9 - 80e9 = 614e9
        # EV/Sales = 614e9 / 350e9 = 1.75428...
        result = ev_sales_metric.ev_sales_at("PETR4", "2024-06-30")
        expected = (38.0 * 13e9 + 200e9 - 80e9) / 350e9
        assert result == pytest.approx(expected, rel=1e-3)

    def test_missing_price_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.price_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.cash_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.revenue_at", lambda c, d: 350e9)
        assert ev_sales_metric.ev_sales_at("PETR4", "2024-06-30") is None

    def test_missing_revenue_none(self, monkeypatch):
        """Missing numerator (revenue) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.cash_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.revenue_at", lambda c, d: None)
        assert ev_sales_metric.ev_sales_at("PETR4", "2024-06-30") is None

    def test_zero_revenue_none(self, monkeypatch):
        """revenue <= 0 -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.cash_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.revenue_at", lambda c, d: 0)
        assert ev_sales_metric.ev_sales_at("PETR4", "2024-06-30") is None

    def test_negative_ev_none(self, monkeypatch):
        """EV <= 0 (cash > market_cap + debt) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.debt_at", lambda c, d: 100e9)
        # cash = 100e9 + 494e9 + 1 = bigger than market_cap + debt -> EV negative
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.cash_at", lambda c, d: 700e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.revenue_at", lambda c, d: 350e9)
        assert ev_sales_metric.ev_sales_at("PETR4", "2024-06-30") is None

    def test_missing_debt_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.debt_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.cash_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_sales.revenue_at", lambda c, d: 350e9)
        assert ev_sales_metric.ev_sales_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["ev_sales"].ratio_key == "ev_sales"
        assert METRICS["ev_sales"].per_share_key is None
        assert resolve_metric("ev_receita").name == "ev_sales"
        assert resolve_metric("ev_vendas").name == "ev_sales"
        assert resolve_metric("evs").name == "ev_sales"
        assert METRICS["ev_sales"].engines == ["price", "shares", "debt", "cash", "revenue"]
