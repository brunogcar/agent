"""Tests for P/FCO (Price-to-Operating-Cash-Flow) metric.

P/FCO = price / (FCO / shares). Guards: FCO <= 0 → None.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import p_fco as p_fco_metric


class TestPFcoAt:
    def test_basic_computation(self, monkeypatch):
        """p_fco_at = price / (FCO / shares)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.operating_cf_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.shares_at", lambda c, d: 13e9)
        # FCO/share = 280e9 / 13e9 = 21.538...
        # P/FCO = 38.0 / 21.538 = 1.764...
        result = p_fco_metric.p_fco_at("PETR4", "2024-06-30")
        assert result == pytest.approx(38.0 / (280e9 / 13e9), rel=1e-3)

    def test_fco_per_share(self, monkeypatch):
        """fco_ps_at = FCO / shares."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.operating_cf_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.shares_at", lambda c, d: 13e9)
        result = p_fco_metric.fco_ps_at("PETR4", "2024-06-30")
        assert result == pytest.approx(280e9 / 13e9, rel=1e-3)

    def test_negative_fco_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.operating_cf_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.shares_at", lambda c, d: 13e9)
        assert p_fco_metric.p_fco_at("PETR4", "2024-06-30") is None

    def test_missing_price_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.operating_cf_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.shares_at", lambda c, d: 13e9)
        assert p_fco_metric.p_fco_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["p_fco"].ratio_key == "p_fco"
        assert METRICS["p_fco"].per_share_key == "fco_ps"
        assert resolve_metric("preco_fco").name == "p_fco"
