"""Tests for P/FCF (Price-to-Free-Cash-Flow) metric.

P/FCF = price / ((FCO + FCI) / shares). Guards: FCF <= 0 → None.
Includes FCO/FCI date alignment guard test (periods must resolve to same date).
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import p_fcf as p_fcf_metric


class TestPFcfAt:
    def test_basic_computation(self, monkeypatch):
        """p_fcf_at = price / ((FCO + FCI) / shares)."""
        # Mock the periods functions (fcf_ps_at uses operating_cf_periods + investing_cf_periods)
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.price_at", lambda t, d: 38.0)
        # FCF = 280e9 + (-100e9) = 180e9
        # FCF/share = 180e9 / 13e9 = 13.846...
        # P/FCF = 38.0 / 13.846 = 2.744...
        result = p_fcf_metric.p_fcf_at("PETR4", "2024-07-15")
        assert result == pytest.approx(38.0 / (180e9 / 13e9), rel=1e-3)

    def test_fcf_per_share(self, monkeypatch):
        """fcf_ps_at = (FCO + FCI) / shares."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        # FCF = 180e9, FCF/share = 180e9/13e9 = 13.846...
        result = p_fcf_metric.fcf_ps_at("PETR4", "2024-07-15")
        assert result == pytest.approx(180e9 / 13e9, rel=1e-3)

    def test_misaligned_periods_returns_none(self, monkeypatch):
        """FCO and FCI resolve to different dates → None (alignment guard)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.investing_cf_periods",
            lambda c: [{"date": "2024-03-31", "ttm_fci": -100e9}],  # different date!
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.price_at", lambda t, d: 38.0)
        assert p_fcf_metric.fcf_ps_at("PETR4", "2024-07-15") is None

    def test_negative_fcf_none(self, monkeypatch):
        """FCF <= 0 → None (ratio meaningless for cash-burning companies)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 50e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.p_fcf.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],  # FCF = -50e9
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.p_fcf.price_at", lambda t, d: 38.0)
        assert p_fcf_metric.p_fcf_at("PETR4", "2024-07-15") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["p_fcf"].ratio_key == "p_fcf"
        assert METRICS["p_fcf"].per_share_key == "fcf_ps"
        assert resolve_metric("preco_fcf").name == "p_fcf"
