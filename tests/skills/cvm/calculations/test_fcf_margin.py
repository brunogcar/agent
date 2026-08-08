"""Tests for FCF Margin = (FCO + FCI) / Revenue.

[v1.22] Updated mocks to use *_at (was *_periods). Alignment guard removed.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import fcf_margin as fcf_margin_metric


class TestFcfMarginAt:
    def test_basic_computation(self, monkeypatch):
        """fcf_margin_at = (FCO + FCI) / revenue."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        result = fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15")
        assert result == pytest.approx(180e9 / 350e9, rel=1e-3)

    def test_misaligned_periods_returns_none(self, monkeypatch):
        """[v1.22] Alignment guard removed — should NOT return None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        result = fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15")
        assert result is not None

    def test_negative_fcf_none(self, monkeypatch):
        """FCF <= 0 → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_at",
            lambda c, d: 50e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_missing_fco_none(self, monkeypatch):
        """Missing FCO → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: 350e9)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_missing_revenue_none(self, monkeypatch):
        """Missing revenue → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.fcf_margin.revenue_at", lambda c, d: None)
        assert fcf_margin_metric.fcf_margin_at("PETR4", "2024-07-15") is None

    def test_zero_revenue_none(self, monkeypatch):
        """revenue <= 0 → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.fcf_margin.investing_cf_at",
            lambda c, d: -100e9,
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
