"""Tests for Receivables Turnover = Revenue / Receivables.

Fundamental ratio (per_share=None). Guards: receivables > 0; revenue > 0.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import receivables_turnover as rto_metric


class TestReceivablesTurnover:
    def test_basic_computation(self, monkeypatch):
        """revenue / receivables."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: 50e9)
        # 350 / 50 = 7.0
        result = rto_metric.receivables_turnover_at("PETR4", "2024-06-30")
        assert result == pytest.approx(7.0, rel=1e-3)

    def test_missing_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: 50e9)
        assert rto_metric.receivables_turnover_at("PETR4", "2024-06-30") is None

    def test_missing_receivables_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: None)
        assert rto_metric.receivables_turnover_at("PETR4", "2024-06-30") is None

    def test_zero_revenue_none(self, monkeypatch):
        """Zero revenue -> None (numerator must be > 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: 50e9)
        assert rto_metric.receivables_turnover_at("PETR4", "2024-06-30") is None

    def test_negative_revenue_none(self, monkeypatch):
        """Negative revenue (rare -- restatements) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: 50e9)
        assert rto_metric.receivables_turnover_at("PETR4", "2024-06-30") is None

    def test_zero_receivables_none(self, monkeypatch):
        """Zero receivables -> None (denominator)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: 0)
        assert rto_metric.receivables_turnover_at("PETR4", "2024-06-30") is None

    def test_negative_receivables_none(self, monkeypatch):
        """Negative receivables -> None (denominator must be > 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.receivables_turnover.receivables_at",
                            lambda c, d: -5e9)
        assert rto_metric.receivables_turnover_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["receivables_turnover"].ratio_key == "receivables_turnover"
        assert METRICS["receivables_turnover"].per_share_key is None
        assert resolve_metric("giro_contas_receber").name == "receivables_turnover"
        assert resolve_metric("rto").name == "receivables_turnover"
        assert resolve_metric("receivables_turn").name == "receivables_turnover"
