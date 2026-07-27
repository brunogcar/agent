"""Tests for graham_number."""
from __future__ import annotations
import pytest

# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import p_fco as p_fco_metric


class TestPFco:
    def test_basic_computation(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.operating_cf_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.shares_at", lambda c, d: 13e9)
        # FCO/share = 80e9 / 13e9 = 6.1538...
        # P/FCO = 38.0 / 6.1538 = 6.175...
        result = p_fco_metric.p_fco_at("PETR4", "2024-06-30")
        assert result == pytest.approx(38.0 / (80e9 / 13e9), rel=1e-3)

    def test_negative_fco_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.operating_cf_at", lambda c, d: -5e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fco.shares_at", lambda c, d: 13e9)
        assert p_fco_metric.p_fco_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["p_fco"].ratio_key == "p_fco"
        assert METRICS["p_fco"].per_share_key == "fco_ps"
        assert resolve_metric("preco_fco").name == "p_fco"


