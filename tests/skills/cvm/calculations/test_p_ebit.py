"""Tests for P/EBIT (Price-to-EBIT) metric.

P/EBIT = price / (EBIT / shares). Guards: EBIT <= 0 → None.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import p_ebit as p_ebit_metric


class TestPEbitAt:
    def test_basic_computation(self, monkeypatch):
        """p_ebit_at = price / (EBIT / shares)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.shares_at", lambda c, d: 13e9)
        # EBIT/share = 70e9 / 13e9 = 5.3846...
        # P/EBIT = 38.0 / 5.3846 = 7.054...
        result = p_ebit_metric.p_ebit_at("PETR4", "2024-06-30")
        assert result == pytest.approx(38.0 / (70e9 / 13e9), rel=1e-3)

    def test_ebit_per_share(self, monkeypatch):
        """ebit_ps_at = EBIT / shares."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.shares_at", lambda c, d: 13e9)
        result = p_ebit_metric.ebit_ps_at("PETR4", "2024-06-30")
        assert result == pytest.approx(70e9 / 13e9, rel=1e-3)

    def test_negative_ebit_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.ebit_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.shares_at", lambda c, d: 13e9)
        assert p_ebit_metric.p_ebit_at("PETR4", "2024-06-30") is None

    def test_missing_price_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_ebit.shares_at", lambda c, d: 13e9)
        assert p_ebit_metric.p_ebit_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["p_ebit"].ratio_key == "p_ebit"
        assert METRICS["p_ebit"].per_share_key == "ebit_ps"
        assert resolve_metric("preco_ebit").name == "p_ebit"
