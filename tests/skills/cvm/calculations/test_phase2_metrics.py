"""Tests for Phase 2A new engines + metrics.

Tests: operating_cf engine, investing_cf engine, p_ebit, p_fco, p_fcf,
graham_number metrics.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# P/EBIT metric (per-share + ratio, dual-axis)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import p_ebit as p_ebit_metric


class TestPEbit:
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

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["p_ebit"].ratio_key == "p_ebit"
        assert METRICS["p_ebit"].per_share_key == "ebit_ps"
        assert resolve_metric("preco_ebit").name == "p_ebit"


# ════════════════════════════════════════════════════════════════════════════
# P/FCO metric (per-share + ratio, dual-axis)
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


# ════════════════════════════════════════════════════════════════════════════
# P/FCF metric (FCF = FCO + FCI, per-share + ratio, dual-axis)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import p_fcf as p_fcf_metric


class TestPFcf:
    def test_basic_computation(self, monkeypatch):
        """FCF = FCO + FCI. FCI is typically negative."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.operating_cf_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.investing_cf_at", lambda c, d: -30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        # FCF = 80e9 + (-30e9) = 50e9
        # FCF/share = 50e9 / 13e9 = 3.846...
        # P/FCF = 38.0 / 3.846 = 9.88...
        result = p_fcf_metric.p_fcf_at("PETR4", "2024-06-30")
        assert result == pytest.approx(38.0 / (50e9 / 13e9), rel=1e-3)

    def test_fcf_per_share(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.operating_cf_at", lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.investing_cf_at", lambda c, d: -30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        result = p_fcf_metric.fcf_ps_at("PETR4", "2024-06-30")
        assert result == pytest.approx(50e9 / 13e9, rel=1e-3)

    def test_negative_fcf_none(self, monkeypatch):
        """FCF < 0 (FCO < |FCI|) -> P/FCF meaningless -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.operating_cf_at", lambda c, d: 20e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.investing_cf_at", lambda c, d: -30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        assert p_fcf_metric.p_fcf_at("PETR4", "2024-06-30") is None

    def test_missing_fco_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.operating_cf_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.investing_cf_at", lambda c, d: -30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        assert p_fcf_metric.p_fcf_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["p_fcf"].ratio_key == "p_fcf"
        assert METRICS["p_fcf"].per_share_key == "fcf_ps"
        assert resolve_metric("preco_fcf").name == "p_fcf"


# ════════════════════════════════════════════════════════════════════════════
# Graham Number (fundamental ratio)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import graham_number as graham_metric


class TestGrahamNumber:
    def test_basic_computation(self, monkeypatch):
        """Graham Number = sqrt(22.5 * EPS * VPA) = sqrt(22.5 * (earnings/shares) * (pl/shares))."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.ttm_earnings_at", lambda c, d: 120e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.shares_at", lambda c, d: 13e9)
        # LPA = 120e9 / 13e9 = 9.2307...
        # VPA = 350e9 / 13e9 = 26.923...
        # Graham = sqrt(22.5 * 9.2307 * 26.923) = sqrt(5596.15...) = 74.8...
        lpa = 120e9 / 13e9
        vpa = 350e9 / 13e9
        expected = (22.5 * lpa * vpa) ** 0.5
        result = graham_metric.graham_number_at("PETR4", "2024-06-30")
        assert result == pytest.approx(expected, rel=1e-3)

    def test_negative_earnings_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.ttm_earnings_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.pl_at", lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.shares_at", lambda c, d: 13e9)
        assert graham_metric.graham_number_at("PETR4", "2024-06-30") is None

    def test_negative_pl_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.ttm_earnings_at", lambda c, d: 120e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.pl_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.graham_number.shares_at", lambda c, d: 13e9)
        assert graham_metric.graham_number_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["graham_number"].ratio_key == "graham_number"
        assert METRICS["graham_number"].per_share_key is None
        assert resolve_metric("graham").name == "graham_number"
        assert resolve_metric("numero_graham").name == "graham_number"


# ════════════════════════════════════════════════════════════════════════════
# Engine registration tests
# ════════════════════════════════════════════════════════════════════════════

class TestNewEngineRegistration:
    def test_operating_cf_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "operating_cf" in ENGINES
        assert ENGINES["operating_cf"].category == "dfc"
        assert ENGINES["operating_cf"].quantity == "ttm_fco"

    def test_investing_cf_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "investing_cf" in ENGINES
        assert ENGINES["investing_cf"].category == "dfc"
        assert ENGINES["investing_cf"].quantity == "ttm_fci"

    def test_dfc_category_has_4_engines(self):
        from skills.cvm.calculations._registry import list_engines
        dfc_engines = list_engines(category="dfc")
        assert "da" in dfc_engines
        assert "capex" in dfc_engines
        assert "operating_cf" in dfc_engines
        assert "investing_cf" in dfc_engines
        assert len(dfc_engines) == 4
