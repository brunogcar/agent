"""Tests for v1.7 new metrics: ROA, Gross Margin, Operating Margin.

All 3 are fundamental ratios (no price, no shares) following the ROE pattern.
Tests mirror test_roe.py structure.

Also tests the 3 new engines: assets, gross_profit, ebit.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# ROA (Return on Assets = earnings / assets)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import roa as roa_metric


class TestRoaAt:
    def test_basic_computation(self, monkeypatch):
        """roa_at = TTM earnings / total assets."""
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.ttm_earnings_at", lambda c, d: 120e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.assets_at", lambda c, d: 800e9)
        # ROA = 120e9 / 800e9 = 0.15
        result = roa_metric.roa_at("PETR4", "2024-06-30")
        assert result == pytest.approx(0.15, rel=1e-3)

    def test_missing_earnings(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.ttm_earnings_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.assets_at", lambda c, d: 800e9)
        assert roa_metric.roa_at("PETR4", "2024-06-30") is None

    def test_missing_assets(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.ttm_earnings_at", lambda c, d: 120e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.assets_at", lambda c, d: None)
        assert roa_metric.roa_at("PETR4", "2024-06-30") is None

    def test_negative_earnings_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.ttm_earnings_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.assets_at", lambda c, d: 800e9)
        assert roa_metric.roa_at("PETR4", "2024-06-30") is None


class TestRoaHistory:
    def test_basic_shape(self, monkeypatch):
        """roa_history should return series with roa, ttm_earnings, assets (no price/shares)."""
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.roa.ttm_earnings_periods",
            lambda c: [{"date": "2024-03-31", "ttm": 120e9}, {"date": "2024-06-30", "ttm": 130e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.roa.assets_periods",
            lambda c: [{"date": "2024-03-31", "assets": 800e9}, {"date": "2024-06-30", "assets": 820e9}],
        )
        result = roa_metric.roa_history("PETR4", "2024-01-01", "2024-12-31")
        assert len(result) >= 2
        for entry in result:
            assert "date" in entry
            assert "roa" in entry
            assert "ttm_earnings" in entry
            assert "assets" in entry
            assert "price" not in entry
            assert "shares" not in entry

    def test_empty_periods_returns_empty(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.ttm_earnings_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.historical.metrics.roa.assets_periods", lambda c: [])
        assert roa_metric.roa_history("PETR4", "2024-01-01", "2024-12-31") == []


class TestRoaRegistry:
    def test_roa_registered(self):
        from skills.cvm.historical._registry import METRICS
        spec = METRICS["roa"]
        assert spec.ratio_key == "roa"
        assert spec.ratio_label == "ROA"
        assert spec.per_share_key is None
        assert "earnings" in spec.engines
        assert "assets" in spec.engines

    def test_roa_aliases(self):
        from skills.cvm.historical._registry import resolve_metric
        assert resolve_metric("return_on_assets").name == "roa"
        assert resolve_metric("retorno_ativos").name == "roa"


# ════════════════════════════════════════════════════════════════════════════
# Gross Margin (= gross_profit / revenue)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import gross_margin as gm_metric


class TestGrossMarginAt:
    def test_basic_computation(self, monkeypatch):
        """gross_margin_at = TTM gross profit / TTM revenue."""
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.gross_profit_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.revenue_at", lambda c, d: 280e9)
        # Gross Margin = 100e9 / 280e9 = 0.357...
        result = gm_metric.gross_margin_at("PETR4", "2024-06-30")
        assert result == pytest.approx(100e9 / 280e9, rel=1e-3)

    def test_missing_gross_profit(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.gross_profit_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.revenue_at", lambda c, d: 280e9)
        assert gm_metric.gross_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.gross_profit_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.revenue_at", lambda c, d: None)
        assert gm_metric.gross_margin_at("PETR4", "2024-06-30") is None

    def test_negative_gross_profit_returns_none(self, monkeypatch):
        """Negative gross profit (selling below cost) -> None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.gross_profit_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.gross_margin.revenue_at", lambda c, d: 280e9)
        assert gm_metric.gross_margin_at("PETR4", "2024-06-30") is None


class TestGrossMarginHistory:
    def test_basic_shape(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.gross_margin.gross_profit_periods",
            lambda c: [{"date": "2024-03-31", "ttm_gp": 100e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.gross_margin.revenue_periods",
            lambda c: [{"date": "2024-03-31", "ttm_rev": 280e9}],
        )
        result = gm_metric.gross_margin_history("PETR4", "2024-01-01", "2024-12-31")
        assert len(result) >= 1
        for entry in result:
            assert "date" in entry
            assert "gross_margin" in entry
            assert "ttm_gp" in entry
            assert "ttm_rev" in entry
            assert "price" not in entry


class TestGrossMarginRegistry:
    def test_gross_margin_registered(self):
        from skills.cvm.historical._registry import METRICS
        spec = METRICS["gross_margin"]
        assert spec.ratio_key == "gross_margin"
        assert spec.ratio_label == "Margem Bruta"
        assert spec.per_share_key is None
        assert "gross_profit" in spec.engines
        assert "revenue" in spec.engines

    def test_gross_margin_aliases(self):
        from skills.cvm.historical._registry import resolve_metric
        assert resolve_metric("margem_bruta").name == "gross_margin"
        assert resolve_metric("gm").name == "gross_margin"
        assert resolve_metric("gross_margin_pct").name == "gross_margin"


# ════════════════════════════════════════════════════════════════════════════
# Operating Margin (= EBIT / revenue)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import operating_margin as om_metric


class TestOperatingMarginAt:
    def test_basic_computation(self, monkeypatch):
        """operating_margin_at = TTM EBIT / TTM revenue."""
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.revenue_at", lambda c, d: 280e9)
        # Operating Margin = 70e9 / 280e9 = 0.25
        result = om_metric.operating_margin_at("PETR4", "2024-06-30")
        assert result == pytest.approx(0.25, rel=1e-3)

    def test_missing_ebit(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.ebit_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.revenue_at", lambda c, d: 280e9)
        assert om_metric.operating_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.revenue_at", lambda c, d: None)
        assert om_metric.operating_margin_at("PETR4", "2024-06-30") is None

    def test_negative_ebit_returns_none(self, monkeypatch):
        """Operating losses -> None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.ebit_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.operating_margin.revenue_at", lambda c, d: 280e9)
        assert om_metric.operating_margin_at("PETR4", "2024-06-30") is None


class TestOperatingMarginHistory:
    def test_basic_shape(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.operating_margin.ebit_periods",
            lambda c: [{"date": "2024-03-31", "ttm_ebit": 70e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.operating_margin.revenue_periods",
            lambda c: [{"date": "2024-03-31", "ttm_rev": 280e9}],
        )
        result = om_metric.operating_margin_history("PETR4", "2024-01-01", "2024-12-31")
        assert len(result) >= 1
        for entry in result:
            assert "date" in entry
            assert "operating_margin" in entry
            assert "ttm_ebit" in entry
            assert "ttm_rev" in entry
            assert "price" not in entry


class TestOperatingMarginRegistry:
    def test_operating_margin_registered(self):
        from skills.cvm.historical._registry import METRICS
        spec = METRICS["operating_margin"]
        assert spec.ratio_key == "operating_margin"
        assert spec.ratio_label == "Margem Operacional"
        assert spec.per_share_key is None
        assert "ebit" in spec.engines
        assert "revenue" in spec.engines

    def test_operating_margin_aliases(self):
        from skills.cvm.historical._registry import resolve_metric
        assert resolve_metric("margem_operacional").name == "operating_margin"
        assert resolve_metric("om").name == "operating_margin"
        assert resolve_metric("operating_margin_pct").name == "operating_margin"


# ════════════════════════════════════════════════════════════════════════════
# Engine registration tests
# ════════════════════════════════════════════════════════════════════════════

class TestNewEngineRegistration:
    def test_assets_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "assets" in ENGINES
        assert ENGINES["assets"].category == "bpa"
        assert ENGINES["assets"].quantity == "assets"

    def test_gross_profit_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "gross_profit" in ENGINES
        assert ENGINES["gross_profit"].category == "dre"
        assert ENGINES["gross_profit"].quantity == "ttm_gp"

    def test_ebit_registered(self):
        from skills.cvm.historical._registry import ENGINES
        assert "ebit" in ENGINES
        assert ENGINES["ebit"].category == "dre"
        assert ENGINES["ebit"].quantity == "ttm_ebit"

    def test_bpa_category_has_assets(self):
        from skills.cvm.historical._registry import list_engines
        bpa_engines = list_engines(category="bpa")
        assert "assets" in bpa_engines

    def test_dre_category_has_engines(self):
        from skills.cvm.historical._registry import list_engines
        dre_engines = list_engines(category="dre")
        assert "earnings" in dre_engines
        assert "revenue" in dre_engines
        assert "gross_profit" in dre_engines
        assert "ebit" in dre_engines
        assert len(dre_engines) >= 4  # v1.7 had 4, v1.8 added tax (5)
