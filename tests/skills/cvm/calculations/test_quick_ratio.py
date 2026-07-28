"""Tests for Quick Ratio = (Cash + Receivables) / Current Liabilities.

Fundamental ratio (per_share=None). Guards: current_liabilities > 0;
cash and receivables may each be 0; if either is None return None.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import quick_ratio as qr_metric


class TestQuickRatio:
    def test_basic_computation(self, monkeypatch):
        """(cash + receivables) / current_liabilities."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: 120e9)
        # (80 + 50) / 120 = 130/120 = 1.0833...
        result = qr_metric.quick_ratio_at("PETR4", "2024-06-30")
        assert result == pytest.approx(130e9 / 120e9, rel=1e-3)

    def test_zero_cash_valid(self, monkeypatch):
        """Zero cash is valid -- ratio uses receivables only."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: 120e9)
        # (0 + 50) / 120 = 0.41666...
        result = qr_metric.quick_ratio_at("PETR4", "2024-06-30")
        assert result == pytest.approx(50e9 / 120e9, rel=1e-3)

    def test_zero_receivables_valid(self, monkeypatch):
        """Zero receivables is valid -- ratio uses cash only."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: 120e9)
        # (80 + 0) / 120 = 0.66666...
        result = qr_metric.quick_ratio_at("PETR4", "2024-06-30")
        assert result == pytest.approx(80e9 / 120e9, rel=1e-3)

    def test_missing_cash_none(self, monkeypatch):
        """Missing cash (None) -- incomplete numerator, return None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: 120e9)
        assert qr_metric.quick_ratio_at("PETR4", "2024-06-30") is None

    def test_missing_receivables_none(self, monkeypatch):
        """Missing receivables (None) -- incomplete numerator, return None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: 120e9)
        assert qr_metric.quick_ratio_at("PETR4", "2024-06-30") is None

    def test_missing_current_liabilities_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: None)
        assert qr_metric.quick_ratio_at("PETR4", "2024-06-30") is None

    def test_zero_current_liabilities_none(self, monkeypatch):
        """Zero denominator -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: 0)
        assert qr_metric.quick_ratio_at("PETR4", "2024-06-30") is None

    def test_negative_current_liabilities_none(self, monkeypatch):
        """Negative current liabilities -> None (denominator must be > 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.cash_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.receivables_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.quick_ratio.current_liabilities_at",
                            lambda c, d: -10e9)
        assert qr_metric.quick_ratio_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["quick_ratio"].ratio_key == "quick_ratio"
        assert METRICS["quick_ratio"].per_share_key is None
        assert resolve_metric("liquidez_seca").name == "quick_ratio"
        assert resolve_metric("acid_test").name == "quick_ratio"
        assert resolve_metric("qr").name == "quick_ratio"
