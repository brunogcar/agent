"""Tests for ROA (Return on Assets = earnings / assets).

Fundamental ratio (no price, no shares) following the ROE pattern.
Mirrors test_roe.py structure.

Also covered in this file:
  - TestRoaAt: roa_at computation + edge cases
  - TestRoaHistory: roa_history shape + empty periods
  - TestRoaRegistry: registry spec + aliases

Engine registration (assets engine) lives in test_engines.py.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# ROA (Return on Assets = earnings / assets)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import roa as roa_metric


class TestRoaAt:
    def test_basic_computation(self, monkeypatch):
        """roa_at = TTM earnings / total assets."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.ttm_earnings_at", lambda c, d: 120e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.assets_at", lambda c, d: 800e9)
        # ROA = 120e9 / 800e9 = 0.15
        result = roa_metric.roa_at("PETR4", "2024-06-30")
        assert result == pytest.approx(0.15, rel=1e-3)

    def test_missing_earnings(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.ttm_earnings_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.assets_at", lambda c, d: 800e9)
        assert roa_metric.roa_at("PETR4", "2024-06-30") is None

    def test_missing_assets(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.ttm_earnings_at", lambda c, d: 120e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.assets_at", lambda c, d: None)
        assert roa_metric.roa_at("PETR4", "2024-06-30") is None

    def test_negative_earnings_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.ttm_earnings_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.assets_at", lambda c, d: 800e9)
        assert roa_metric.roa_at("PETR4", "2024-06-30") is None


class TestRoaHistory:
    def test_basic_shape(self, monkeypatch):
        """roa_history should return series with roa, ttm_earnings, assets (no price/shares)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roa.ttm_earnings_periods",
            lambda c: [{"date": "2024-03-31", "ttm": 120e9}, {"date": "2024-06-30", "ttm": 130e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roa.assets_periods",
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
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.ttm_earnings_periods", lambda c: [])
        monkeypatch.setattr("skills.cvm.calculations.metrics.roa.assets_periods", lambda c: [])
        assert roa_metric.roa_history("PETR4", "2024-01-01", "2024-12-31") == []


class TestRoaRegistry:
    def test_roa_registered(self):
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["roa"]
        assert spec.ratio_key == "roa"
        assert spec.ratio_label == "ROA"
        assert spec.per_share_key is None
        assert "earnings" in spec.engines
        assert "assets" in spec.engines

    def test_roa_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("return_on_assets").name == "roa"
        assert resolve_metric("retorno_ativos").name == "roa"
