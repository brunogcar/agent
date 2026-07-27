"""Tests for Net Margin = earnings / revenue.

Fundamental ratio (per_share=None) composing existing engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Net Margin = earnings / revenue
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import net_margin as nm_metric


class TestNetMargin:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_margin.ttm_earnings_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_margin.revenue_at", lambda c, d: 280e9)
        assert nm_metric.net_margin_at("PETR4", "2024-06-30") == pytest.approx(0.25, rel=1e-3)

    def test_negative_earnings_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_margin.ttm_earnings_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_margin.revenue_at", lambda c, d: 280e9)
        assert nm_metric.net_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_margin.ttm_earnings_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_margin.revenue_at", lambda c, d: None)
        assert nm_metric.net_margin_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["net_margin"].ratio_key == "net_margin"
        assert METRICS["net_margin"].per_share_key is None
        assert resolve_metric("margem_liquida").name == "net_margin"
        assert resolve_metric("ml").name == "net_margin"
