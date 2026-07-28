"""Tests for Fixed Asset Turnover = Revenue / PP&E.

Fundamental ratio (per_share=None). Guards: ppe > 0; revenue > 0.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import fixed_asset_turnover as fato_metric


class TestFixedAssetTurnover:
    def test_basic_computation(self, monkeypatch):
        """revenue / ppe."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: 230e9)
        # 350 / 230 = 1.5217...
        result = fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30")
        assert result == pytest.approx(350e9 / 230e9, rel=1e-3)

    def test_missing_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: 230e9)
        assert fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30") is None

    def test_missing_ppe_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: None)
        assert fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30") is None

    def test_zero_revenue_none(self, monkeypatch):
        """Zero revenue -> None (numerator must be > 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: 230e9)
        assert fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30") is None

    def test_negative_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: 230e9)
        assert fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30") is None

    def test_zero_ppe_none(self, monkeypatch):
        """Zero PP&E -> None (denominator)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: 0)
        assert fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30") is None

    def test_negative_ppe_none(self, monkeypatch):
        """Negative PP&E -> None (denominator must be > 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: -5e9)
        assert fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30") is None

    def test_asset_light_high_turnover(self, monkeypatch):
        """Sanity: asset-light company -> high fixed-asset turnover."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.revenue_at",
                            lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.fixed_asset_turnover.ppe_at",
                            lambda c, d: 5e9)
        result = fato_metric.fixed_asset_turnover_at("PETR4", "2024-06-30")
        assert result == pytest.approx(20.0, rel=1e-3)

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["fixed_asset_turnover"].ratio_key == "fixed_asset_turnover"
        assert METRICS["fixed_asset_turnover"].per_share_key is None
        assert resolve_metric("giro_imobilizado").name == "fixed_asset_turnover"
        assert resolve_metric("fato").name == "fixed_asset_turnover"
        assert resolve_metric("fat").name == "fixed_asset_turnover"
        assert resolve_metric("fixed_asset_turn").name == "fixed_asset_turnover"
