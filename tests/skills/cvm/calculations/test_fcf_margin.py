"""Tests for FCF Margin = (FCO + FCI) / Revenue.

Type 2 fundamental ratio with FCO/FCI date-alignment guard (same pattern
as test_p_fcf.py). Mocks the *_periods() functions (not *_at()) for FCO/FCI.
Guards: FCF <= 0 -> None, revenue <= 0 -> None, misaligned periods -> None.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import fcf_margin as fcf_margin_metric


class TestFcfMarginAt:
    def test_basic_computation(self, monkeypatch):
        """fcf_margin_at = (FCO + FCI) / revenue."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        # FCF = 280e9 - 100e9 = 180e9
        # FCF Margin = 180e9 / 350e9 = 0.51428...
        result = fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15")
        assert result == pytest.approx(180e9 / 350e9, rel=1e-3)

    def test_misaligned_periods_returns_none(self, monkeypatch):
        """FCO and FCI resolve to different dates -> None (alignment guard)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_periods",
            lambda c: [{"date": "2024-03-31", "ttm_fci": -100e9}],  # different date!
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_negative_fcf_none(self, monkeypatch):
        """FCF <= 0 -> None (ratio meaningless for cash-burning companies)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 50e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],  # FCF = -50e9
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_missing_fco_none(self, monkeypatch):
        """Missing numerator (FCO via empty periods list) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_periods",
            lambda c: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_missing_revenue_none(self, monkeypatch):
        """Missing denominator (revenue) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: None)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_zero_revenue_none(self, monkeypatch):
        """revenue <= 0 -> None (denominator guard)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fco": 280e9}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_periods",
            lambda c: [{"date": "2024-06-30", "ttm_fci": -100e9}],
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 0)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["fcf_margin"].ratio_key == "fcf_margin"
        assert METRICS["fcf_margin"].per_share_key is None
        assert resolve_metric("margem_fcf").name == "fcf_margin"
        assert resolve_metric("fcf_margem").name == "fcf_margin"
        assert METRICS["fcf_margin"].engines == ["operating_cf", "investing_cf", "revenue"]
