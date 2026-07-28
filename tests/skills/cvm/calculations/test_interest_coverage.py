"""Tests for Interest Coverage Ratio = EBIT / abs(financial_result).

Fundamental ratio (per_share=None). Guards: EBIT > 0; financial_result
must be < 0 (net expense). Returns None when financial_result >= 0
(net income -- no interest expense to cover).
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import interest_coverage as ic_metric


class TestInterestCoverage:
    def test_basic_computation(self, monkeypatch):
        """EBIT / abs(financial_result) where financial_result is net expense."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: -10e9)
        # 50 / 10 = 5.0
        result = ic_metric.interest_coverage_at("PETR4", "2024-06-30")
        assert result == pytest.approx(5.0, rel=1e-3)

    def test_positive_financial_result_none(self, monkeypatch):
        """Net financial income (positive) -> None (no expense to cover)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: 5e9)
        assert ic_metric.interest_coverage_at("PETR4", "2024-06-30") is None

    def test_zero_financial_result_none(self, monkeypatch):
        """Zero financial result -> None (no expense to cover)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: 0)
        assert ic_metric.interest_coverage_at("PETR4", "2024-06-30") is None

    def test_zero_ebit_none(self, monkeypatch):
        """EBIT = 0 -> None (can't cover anything)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: -10e9)
        assert ic_metric.interest_coverage_at("PETR4", "2024-06-30") is None

    def test_negative_ebit_none(self, monkeypatch):
        """Negative EBIT -> None (operating loss -- can't cover interest)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: -5e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: -10e9)
        assert ic_metric.interest_coverage_at("PETR4", "2024-06-30") is None

    def test_missing_ebit_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: -10e9)
        assert ic_metric.interest_coverage_at("PETR4", "2024-06-30") is None

    def test_missing_financial_result_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: None)
        assert ic_metric.interest_coverage_at("PETR4", "2024-06-30") is None

    def test_large_ebit_small_expense_high_ratio(self, monkeypatch):
        """Sanity check on extreme values: tiny expense yields very high ICR."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.ebit_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.interest_coverage.financial_result_at",
                            lambda c, d: -1e6)
        result = ic_metric.interest_coverage_at("PETR4", "2024-06-30")
        assert result == pytest.approx(50e9 / 1e6, rel=1e-3)
        assert result > 1000  # very high coverage

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["interest_coverage"].ratio_key == "interest_coverage"
        assert METRICS["interest_coverage"].per_share_key is None
        assert resolve_metric("cobertura_juros").name == "interest_coverage"
        assert resolve_metric("ic").name == "interest_coverage"
        assert resolve_metric("icr").name == "interest_coverage"
        assert resolve_metric("cobertura_despesa_financeira").name == "interest_coverage"
