"""Tests for Current Ratio metric (= current_assets / current_liabilities).

Fundamental ratio (per_share=None) composing assets + current_liabilities engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Current Ratio
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import current_ratio as crr_metric


class TestCurrentRatio:
    def test_basic(self, monkeypatch):
        """current_ratio = current_assets / current_liabilities."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.assets_at", lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.current_liabilities_at", lambda c, d: 100e9)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") == pytest.approx(1.5, rel=1e-3)

    def test_missing_assets_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.assets_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.current_liabilities_at", lambda c, d: 100e9)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") is None

    def test_missing_liabilities_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.assets_at", lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.current_liabilities_at", lambda c, d: None)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") is None

    def test_zero_liabilities_none(self, monkeypatch):
        """Zero liabilities -> division by zero -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.assets_at", lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.current_ratio.current_liabilities_at", lambda c, d: 0)
        assert crr_metric.current_ratio_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["current_ratio"].ratio_key == "current_ratio"
        assert METRICS["current_ratio"].per_share_key is None
        assert resolve_metric("liquidez_corrente").name == "current_ratio"
        assert resolve_metric("cr").name == "current_ratio"
