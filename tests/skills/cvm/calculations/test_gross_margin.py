"""Tests for Gross Margin (= gross_profit / revenue).

Fundamental ratio (no price, no shares) following the ROE pattern.
Mirrors test_roe.py structure.

Contains:
  - TestGrossMarginAt: computation + edge cases
  - TestGrossMarginHistory: shape verification
  - TestGrossMarginRegistry: spec + aliases

Engine registration (gross_profit engine) lives in test_engines.py.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Gross Margin (= gross_profit / revenue)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import gross_margin as gm_metric


class TestGrossMarginAt:
    def test_basic_computation(self, monkeypatch):
        """gross_margin_at = TTM gross profit / TTM revenue."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.gross_profit_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.revenue_at", lambda c, d: 280e9)
        # Gross Margin = 100e9 / 280e9 = 0.357...
        result = gm_metric.gross_margin_at("PETR4", "2024-06-30")
        assert result == pytest.approx(100e9 / 280e9, rel=1e-3)

    def test_missing_gross_profit(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.gross_profit_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.revenue_at", lambda c, d: 280e9)
        assert gm_metric.gross_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.gross_profit_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.revenue_at", lambda c, d: None)
        assert gm_metric.gross_margin_at("PETR4", "2024-06-30") is None

    def test_negative_gross_profit_returns_none(self, monkeypatch):
        """Negative gross profit (selling below cost) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.gross_profit_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.gross_margin.revenue_at", lambda c, d: 280e9)
        assert gm_metric.gross_margin_at("PETR4", "2024-06-30") is None


class TestGrossMarginHistory:
    def test_basic_shape(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.gross_margin.gross_profit_periods",
            lambda c: [{"date": "2024-03-31", "ttm_gp": 100e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.gross_margin.revenue_periods",
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
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["gross_margin"]
        assert spec.ratio_key == "gross_margin"
        assert spec.ratio_label == "Margem Bruta"
        assert spec.per_share_key is None
        assert "gross_profit" in spec.engines
        assert "revenue" in spec.engines

    def test_gross_margin_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("margem_bruta").name == "gross_margin"
        assert resolve_metric("gm").name == "gross_margin"
        assert resolve_metric("gross_margin_pct").name == "gross_margin"
