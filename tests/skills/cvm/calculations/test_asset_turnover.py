"""Tests for Asset Turnover = revenue / assets.

Fundamental ratio (per_share=None) composing existing engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Asset Turnover = revenue / assets
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import asset_turnover as at_metric


class TestAssetTurnover:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.asset_turnover.revenue_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.asset_turnover.assets_at", lambda c, d: 800e9)
        assert at_metric.asset_turnover_at("PETR4", "2024-06-30") == pytest.approx(280e9 / 800e9, rel=1e-3)

    def test_missing_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.asset_turnover.revenue_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.asset_turnover.assets_at", lambda c, d: 800e9)
        assert at_metric.asset_turnover_at("PETR4", "2024-06-30") is None

    def test_missing_assets_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.asset_turnover.revenue_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.asset_turnover.assets_at", lambda c, d: None)
        assert at_metric.asset_turnover_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["asset_turnover"].ratio_key == "asset_turnover"
        assert resolve_metric("giro_ativos").name == "asset_turnover"
        assert resolve_metric("at").name == "asset_turnover"
