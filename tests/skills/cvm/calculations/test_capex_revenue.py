"""Tests for CapEx/Revenue metric.

Fundamental ratio (per_share=None) composing capex + revenue engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# CapEx/Revenue
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import capex_revenue as cr_metric


class TestCapexRevenue:
    def test_basic(self, monkeypatch):
        """capex_revenue = CapEx / Revenue (typically negative)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.capex_revenue.capex_at", lambda c, d: -40e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.capex_revenue.revenue_at", lambda c, d: 280e9)
        assert cr_metric.capex_revenue_at("PETR4", "2024-06-30") == pytest.approx(-40e9 / 280e9, rel=1e-3)

    def test_missing_capex_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.capex_revenue.capex_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.capex_revenue.revenue_at", lambda c, d: 280e9)
        assert cr_metric.capex_revenue_at("PETR4", "2024-06-30") is None

    def test_zero_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.capex_revenue.capex_at", lambda c, d: -40e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.capex_revenue.revenue_at", lambda c, d: 0)
        assert cr_metric.capex_revenue_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["capex_revenue"].ratio_key == "capex_revenue"
        assert METRICS["capex_revenue"].per_share_key is None
        assert resolve_metric("capex_intensity").name == "capex_revenue"
        assert resolve_metric("intensidade_capex").name == "capex_revenue"
