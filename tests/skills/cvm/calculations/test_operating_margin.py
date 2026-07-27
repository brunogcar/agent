"""Tests for Operating Margin (= EBIT / revenue).

Fundamental ratio (no price, no shares) following the ROE pattern.
Mirrors test_roe.py structure.

Contains:
  - TestOperatingMarginAt: computation + edge cases
  - TestOperatingMarginHistory: shape verification
  - TestOperatingMarginRegistry: spec + aliases

Engine registration (ebit engine) lives in test_engines.py.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Operating Margin (= EBIT / revenue)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import operating_margin as om_metric


class TestOperatingMarginAt:
    def test_basic_computation(self, monkeypatch):
        """operating_margin_at = TTM EBIT / TTM revenue."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.revenue_at", lambda c, d: 280e9)
        # Operating Margin = 70e9 / 280e9 = 0.25
        result = om_metric.operating_margin_at("PETR4", "2024-06-30")
        assert result == pytest.approx(0.25, rel=1e-3)

    def test_missing_ebit(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.ebit_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.revenue_at", lambda c, d: 280e9)
        assert om_metric.operating_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.revenue_at", lambda c, d: None)
        assert om_metric.operating_margin_at("PETR4", "2024-06-30") is None

    def test_negative_ebit_returns_none(self, monkeypatch):
        """Operating losses -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.ebit_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.operating_margin.revenue_at", lambda c, d: 280e9)
        assert om_metric.operating_margin_at("PETR4", "2024-06-30") is None


class TestOperatingMarginHistory:
    def test_basic_shape(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.operating_margin.ebit_periods",
            lambda c: [{"date": "2024-03-31", "ttm_ebit": 70e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.operating_margin.revenue_periods",
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
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["operating_margin"]
        assert spec.ratio_key == "operating_margin"
        assert spec.ratio_label == "Margem Operacional"
        assert spec.per_share_key is None
        assert "ebit" in spec.engines
        assert "revenue" in spec.engines

    def test_operating_margin_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("margem_operacional").name == "operating_margin"
        assert resolve_metric("om").name == "operating_margin"
        assert resolve_metric("operating_margin_pct").name == "operating_margin"
