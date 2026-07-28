"""Tests for Sustainable Growth Rate = ROE × Retention Ratio.

Type 2 fundamental metric composed from two existing metrics (roe_at +
retention_ratio_at). Mocks the composed metric functions directly.
Guards: ROE <= 0 or None -> None; Retention < 0 or None -> None.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import sustainable_growth as sgr_metric


class TestSustainableGrowthAt:
    def test_basic_computation(self, monkeypatch):
        """SGR = ROE × Retention."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: 0.20,  # 20% ROE
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: 0.50,  # 50% retention
        )
        # SGR = 0.20 × 0.50 = 0.10 (10%)
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") == pytest.approx(0.10, rel=1e-3)

    def test_zero_retention_zero_growth(self, monkeypatch):
        """Retention = 0 (full payout) -> SGR = 0."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: 0.25,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: 0.0,
        )
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") == 0.0

    def test_full_retention(self, monkeypatch):
        """Retention = 1.0 -> SGR = ROE."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: 0.15,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: 1.0,
        )
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") == pytest.approx(0.15, rel=1e-3)

    def test_missing_roe_none(self, monkeypatch):
        """ROE is None -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: 0.50,
        )
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") is None

    def test_missing_retention_none(self, monkeypatch):
        """Retention is None -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: 0.20,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: None,
        )
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") is None

    def test_zero_roe_none(self, monkeypatch):
        """ROE <= 0 -> None (no sustainable internal growth)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: 0.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: 0.50,
        )
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") is None

    def test_negative_roe_none(self, monkeypatch):
        """Negative ROE (loss-making company) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.roe_at",
            lambda c, d: -0.15,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.sustainable_growth.retention_ratio_at",
            lambda c, d: 0.50,
        )
        assert sgr_metric.sustainable_growth_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["sustainable_growth"].ratio_key == "sustainable_growth"
        assert METRICS["sustainable_growth"].per_share_key is None
        assert resolve_metric("crescimento_sustentavel").name == "sustainable_growth"
        assert resolve_metric("sgr").name == "sustainable_growth"
        assert resolve_metric("gs").name == "sustainable_growth"
        # Engines listed = ENGINES composed (earnings + pl from ROE,
        # dividends + earnings from Retention, deduplicated) -- NOT the
        # metrics composed.
        assert METRICS["sustainable_growth"].engines == ["earnings", "pl", "dividends"]
