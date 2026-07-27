"""Tests for Tier 5+6 metrics: CapEx/Revenue, Current Ratio.

Also tests the 3 new engines: capex, total_assets, current_liabilities.
"""
from __future__ import annotations

import pytest
from skills.cvm.historical.metrics import capex_revenue as cr_metric
from skills.cvm.historical.metrics import current_ratio as crr_metric
from skills.cvm.historical.engines import capex as capex_engine
from skills.cvm.historical.engines import total_assets as ta_engine
from skills.cvm.historical.engines import current_liabilities as cl_engine


# ════════════════════════════════════════════════════════════════════════════
# CapEx/Revenue
# ════════════════════════════════════════════════════════════════════════════

class TestCapexRevenue:
    def test_basic(self, monkeypatch):
        """capex_revenue = CapEx / Revenue (typically negative)."""
        monkeypatch.setattr("skills.cvm.historical.metrics.capex_revenue.capex_at", lambda c, d: -40e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.capex_revenue.revenue_at", lambda c, d: 280e9)
        assert cr_metric.capex_revenue_at("PETR4", "2024-06-30") == pytest.approx(-40e9 / 280e9, rel=1e-3)

    def test_missing_capex_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.capex_revenue.capex_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.capex_revenue.revenue_at", lambda c, d: 280e9)
        assert cr_metric.capex_revenue_at("PETR4", "2024-06-30") is None

    def test_zero_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.capex_revenue.capex_at", lambda c, d: -40e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.capex_revenue.revenue_at", lambda c, d: 0)
        assert cr_metric.capex_revenue_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["capex_revenue"].ratio_key == "capex_revenue"
        assert METRICS["capex_revenue"].per_share_key is None
        assert resolve_metric("capex_intensity").name == "capex_revenue"
        assert resolve_metric("intensidade_capex").name == "capex_revenue"


# ════════════════════════════════════════════════════════════════════════════
# Current Ratio
# ════════════════════════════════════════════════════════════════════════════

class TestCurrentRatio:
    def test_basic(self, monkeypatch):
        """current_ratio = current_assets / current_liabilities."""
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.assets_at", lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.current_liabilities_at", lambda c, d: 100e9)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") == pytest.approx(1.5, rel=1e-3)

    def test_missing_assets_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.assets_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.current_liabilities_at", lambda c, d: 100e9)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") is None

    def test_missing_liabilities_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.assets_at", lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.current_liabilities_at", lambda c, d: None)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") is None

    def test_zero_liabilities_none(self, monkeypatch):
        """Zero liabilities -> division by zero -> None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.assets_at", lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.current_ratio.current_liabilities_at", lambda c, d: 0)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["current_ratio"].ratio_key == "current_ratio"
        assert METRICS["current_ratio"].per_share_key is None
        assert resolve_metric("liquidez_corrente").name == "current_ratio"
        assert resolve_metric("cr").name == "current_ratio"


# ════════════════════════════════════════════════════════════════════════════
# Engine registration tests
# ════════════════════════════════════════════════════════════════════════════

class TestNewEngineRegistration:
    def test_capex_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "capex" in ENGINES
        assert ENGINES["capex"].category == "dfc"
        assert ENGINES["capex"].quantity == "ttm_capex"

    def test_total_assets_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "total_assets" in ENGINES
        assert ENGINES["total_assets"].category == "bpa"
        assert ENGINES["total_assets"].quantity == "total_assets"

    def test_current_liabilities_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "current_liabilities" in ENGINES
        assert ENGINES["current_liabilities"].category == "bpp"
        assert ENGINES["current_liabilities"].quantity == "current_liabilities"

    def test_total_engines_is_16(self):
        from skills.cvm.historical._registry import list_engines
        assert len(list_engines()) == 16

    def test_total_metrics_is_17(self):
        from skills.cvm.historical._registry import list_metrics
        assert len(list_metrics()) == 17
