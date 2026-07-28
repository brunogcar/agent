"""Tests for Cash Flow to Debt = FCO / Total Debt.

Type 2 fundamental ratio. Guard: debt <= 0 -> None.
FCO can be negative -- ratio still meaningful (cash-burning company).
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import cash_flow_to_debt as cfd_metric


class TestCashFlowToDebtAt:
    def test_basic_computation(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.operating_cf_at",
            lambda c, d: 120e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.debt_at",
            lambda c, d: 280e9,
        )
        assert cfd_metric.cash_flow_to_debt_at("PETR4", "2024-06-30") == pytest.approx(120e9 / 280e9, rel=1e-3)

    def test_negative_fco(self, monkeypatch):
        """Negative FCO is valid -- ratio is meaningful & negative."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.operating_cf_at",
            lambda c, d: -30e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.debt_at",
            lambda c, d: 280e9,
        )
        result = cfd_metric.cash_flow_to_debt_at("PETR4", "2024-06-30")
        assert result is not None
        assert result < 0
        assert result == pytest.approx(-30e9 / 280e9, rel=1e-3)

    def test_missing_fco_none(self, monkeypatch):
        """Missing numerator (FCO) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.operating_cf_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.debt_at",
            lambda c, d: 280e9,
        )
        assert cfd_metric.cash_flow_to_debt_at("PETR4", "2024-06-30") is None

    def test_missing_debt_none(self, monkeypatch):
        """Missing denominator (debt) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.operating_cf_at",
            lambda c, d: 120e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.debt_at",
            lambda c, d: None,
        )
        assert cfd_metric.cash_flow_to_debt_at("PETR4", "2024-06-30") is None

    def test_zero_debt_none(self, monkeypatch):
        """debt <= 0 -> None (denominator guard)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.operating_cf_at",
            lambda c, d: 120e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.cash_flow_to_debt.debt_at",
            lambda c, d: 0,
        )
        assert cfd_metric.cash_flow_to_debt_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["cash_flow_to_debt"].ratio_key == "cash_flow_to_debt"
        assert METRICS["cash_flow_to_debt"].per_share_key is None
        assert resolve_metric("fco_divida").name == "cash_flow_to_debt"
        assert resolve_metric("cfd").name == "cash_flow_to_debt"
        assert resolve_metric("fluxo_caixa_divida").name == "cash_flow_to_debt"
        assert METRICS["cash_flow_to_debt"].engines == ["operating_cf", "debt"]
