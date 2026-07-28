"""Tests for Cash Ratio = cash / current_liabilities.

Type 2 fundamental ratio. Guard: current_liabilities <= 0 -> None.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import cash_ratio as cash_ratio_metric


class TestCashRatioAt:
    def test_basic_computation(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.cash_ratio.cash_at", lambda c, d: 50e9)
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_ratio.current_liabilities_at",
            lambda c, d: 160e9,
        )
        assert cash_ratio_metric.cash_ratio_at("PETR4", "2024-06-30") == pytest.approx(50e9 / 160e9, rel=1e-3)

    def test_zero_cash(self, monkeypatch):
        """Zero cash is valid (ratio = 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.cash_ratio.cash_at", lambda c, d: 0)
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_ratio.current_liabilities_at",
            lambda c, d: 160e9,
        )
        assert cash_ratio_metric.cash_ratio_at("PETR4", "2024-06-30") == 0.0

    def test_missing_cash_none(self, monkeypatch):
        """Missing numerator (cash) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.cash_ratio.cash_at", lambda c, d: None)
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_ratio.current_liabilities_at",
            lambda c, d: 160e9,
        )
        assert cash_ratio_metric.cash_ratio_at("PETR4", "2024-06-30") is None

    def test_missing_current_liabilities_none(self, monkeypatch):
        """Missing denominator (current_liabilities) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.cash_ratio.cash_at", lambda c, d: 50e9)
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_ratio.current_liabilities_at",
            lambda c, d: None,
        )
        assert cash_ratio_metric.cash_ratio_at("PETR4", "2024-06-30") is None

    def test_zero_current_liabilities_none(self, monkeypatch):
        """current_liabilities <= 0 -> None (denominator guard)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.cash_ratio.cash_at", lambda c, d: 50e9)
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_ratio.current_liabilities_at",
            lambda c, d: 0,
        )
        assert cash_ratio_metric.cash_ratio_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["cash_ratio"].ratio_key == "cash_ratio"
        assert METRICS["cash_ratio"].per_share_key is None
        assert resolve_metric("razao_caixa").name == "cash_ratio"
        assert resolve_metric("cr_caixa").name == "cash_ratio"
        assert METRICS["cash_ratio"].engines == ["cash", "current_liabilities"]
