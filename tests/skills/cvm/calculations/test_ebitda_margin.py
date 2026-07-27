"""Tests for EBITDA Margin = (EBIT + D&A) / revenue.

Fundamental ratio (per_share=None) composing existing engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# EBITDA Margin = (EBIT + D&A) / revenue
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import ebitda_margin as em_metric


class TestEbitdaMargin:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.revenue_at", lambda c, d: 280e9)
        # EBITDA = 85e9, margin = 85e9/280e9 = 0.303...
        assert em_metric.ebitda_margin_at("PETR4", "2024-06-30") == pytest.approx(85e9 / 280e9, rel=1e-3)

    def test_negative_ebitda_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.ebit_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.revenue_at", lambda c, d: 280e9)
        assert em_metric.ebitda_margin_at("PETR4", "2024-06-30") is None

    def test_missing_da_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.da_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ebitda_margin.revenue_at", lambda c, d: 280e9)
        assert em_metric.ebitda_margin_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["ebitda_margin"].ratio_key == "ebitda_margin"
        assert resolve_metric("margem_ebitda").name == "ebitda_margin"
        assert resolve_metric("em").name == "ebitda_margin"
