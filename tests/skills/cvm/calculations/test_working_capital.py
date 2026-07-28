"""Tests for Working Capital = current_assets - current_liabilities.

Type 2 metric (BRL value, not a ratio). Can be NEGATIVE (valid -- retailers).
Returns None if either component is missing.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import working_capital as wc_metric


class TestWorkingCapitalAt:
    def test_basic_computation(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_assets_at",
            lambda c, d: 200e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_liabilities_at",
            lambda c, d: 150e9,
        )
        assert wc_metric.working_capital_at("PETR4", "2024-06-30") == pytest.approx(50e9, rel=1e-3)

    def test_negative_working_capital_valid(self, monkeypatch):
        """Negative working capital is VALID (common for retailers)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_assets_at",
            lambda c, d: 100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_liabilities_at",
            lambda c, d: 180e9,
        )
        result = wc_metric.working_capital_at("PETR4", "2024-06-30")
        assert result is not None
        assert result < 0
        assert result == pytest.approx(-80e9, rel=1e-3)

    def test_zero_working_capital(self, monkeypatch):
        """Equal current_assets and current_liabilities -> WC = 0 (valid)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_assets_at",
            lambda c, d: 150e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_liabilities_at",
            lambda c, d: 150e9,
        )
        assert wc_metric.working_capital_at("PETR4", "2024-06-30") == 0.0

    def test_missing_current_assets_none(self, monkeypatch):
        """Missing current_assets -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_assets_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_liabilities_at",
            lambda c, d: 150e9,
        )
        assert wc_metric.working_capital_at("PETR4", "2024-06-30") is None

    def test_missing_current_liabilities_none(self, monkeypatch):
        """Missing current_liabilities -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_assets_at",
            lambda c, d: 200e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.working_capital.current_liabilities_at",
            lambda c, d: None,
        )
        assert wc_metric.working_capital_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["working_capital"].ratio_key == "working_capital"
        assert METRICS["working_capital"].per_share_key is None
        assert resolve_metric("capital_giro").name == "working_capital"
        assert resolve_metric("giro").name == "working_capital"
        assert resolve_metric("wc").name == "working_capital"
        assert METRICS["working_capital"].engines == ["current_assets", "current_liabilities"]
