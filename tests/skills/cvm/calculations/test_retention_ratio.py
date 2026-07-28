"""Tests for Retention Ratio = 1 - Payout where Payout = Dividends / Earnings.

Type 2 fundamental ratio. Edge cases per task spec:
- earnings <= 0 or None -> None
- dividends is None or 0 -> 1.0 (100% retention)
- payout < 0 -> None (rare anomaly)
- payout > 1 -> 0.0 (clamped)
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import retention_ratio as rr_metric


class TestRetentionRatioAt:
    def test_basic_computation(self, monkeypatch):
        """Payout = 0.42 -> Retention = 0.58."""
        # dividends (DPA) = 1.50, earnings (TTM) = ... pick numbers so payout = 0.42
        # payout = dpa / earnings -> earnings = dpa / payout = 1.50 / 0.42 = 3.5714...
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: 1.50,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: 1.50 / 0.42,
        )
        result = rr_metric.retention_ratio_at("PETR4", "2024-06-30")
        assert result == pytest.approx(0.58, rel=1e-3)

    def test_no_dividends_full_retention(self, monkeypatch):
        """dividends = 0 -> retention = 1.0 (100%)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: 0.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: 10e9,
        )
        assert rr_metric.retention_ratio_at("PETR4", "2024-06-30") == 1.0

    def test_dividends_none_full_retention(self, monkeypatch):
        """dividends is None (no data) -> retention = 1.0 (treat as no dividends)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: 10e9,
        )
        assert rr_metric.retention_ratio_at("PETR4", "2024-06-30") == 1.0

    def test_payout_over_100_percent_clamped_to_zero(self, monkeypatch):
        """payout > 1 (overdistributing) -> retention = 0.0 (clamped)."""
        # dpa = 5.0, earnings = 1.0 -> payout = 5.0 -> retention = 0.0
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: 5.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: 1.0,
        )
        assert rr_metric.retention_ratio_at("PETR4", "2024-06-30") == 0.0

    def test_negative_earnings_none(self, monkeypatch):
        """earnings <= 0 -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: 1.50,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: -5e9,
        )
        assert rr_metric.retention_ratio_at("PETR4", "2024-06-30") is None

    def test_missing_earnings_none(self, monkeypatch):
        """Missing numerator component (earnings) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: 1.50,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: None,
        )
        assert rr_metric.retention_ratio_at("PETR4", "2024-06-30") is None

    def test_full_payout_zero_retention(self, monkeypatch):
        """dpa == earnings -> payout = 1.0 -> retention = 0.0."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.dividends_at",
            lambda c, d: 5.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.retention_ratio.ttm_earnings_at",
            lambda c, d: 5.0,
        )
        assert rr_metric.retention_ratio_at("PETR4", "2024-06-30") == 0.0

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["retention_ratio"].ratio_key == "retention_ratio"
        assert METRICS["retention_ratio"].per_share_key is None
        assert resolve_metric("taxa_retencao").name == "retention_ratio"
        assert resolve_metric("retention").name == "retention_ratio"
        assert resolve_metric("rr").name == "retention_ratio"
        assert METRICS["retention_ratio"].engines == ["dividends", "earnings"]
