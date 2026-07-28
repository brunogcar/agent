"""Tests for OCF Margin = FCO / Revenue.

Type 2 fundamental ratio. Guard: revenue <= 0 -> None.
FCO can be negative (cash-burning company) -- ratio still meaningful & negative.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import ocf_margin as ocf_margin_metric


class TestOcfMarginAt:
    def test_basic_computation(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.operating_cf_at", lambda c, d: 60e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.revenue_at", lambda c, d: 350e9)
        assert ocf_margin_metric.ocf_margin_at("PETR4", "2024-06-30") == pytest.approx(60e9 / 350e9, rel=1e-3)

    def test_negative_fco(self, monkeypatch):
        """Negative FCO is valid -- ratio is meaningful & negative."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.operating_cf_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.revenue_at", lambda c, d: 350e9)
        result = ocf_margin_metric.ocf_margin_at("PETR4", "2024-06-30")
        assert result is not None
        assert result < 0
        assert result == pytest.approx(-20e9 / 350e9, rel=1e-3)

    def test_missing_fco_none(self, monkeypatch):
        """Missing numerator (FCO) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.operating_cf_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.revenue_at", lambda c, d: 350e9)
        assert ocf_margin_metric.ocf_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue_none(self, monkeypatch):
        """Missing denominator (revenue) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.operating_cf_at", lambda c, d: 60e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.revenue_at", lambda c, d: None)
        assert ocf_margin_metric.ocf_margin_at("PETR4", "2024-06-30") is None

    def test_zero_revenue_none(self, monkeypatch):
        """revenue <= 0 -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.operating_cf_at", lambda c, d: 60e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ocf_margin.revenue_at", lambda c, d: 0)
        assert ocf_margin_metric.ocf_margin_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["ocf_margin"].ratio_key == "ocf_margin"
        assert METRICS["ocf_margin"].per_share_key is None
        assert resolve_metric("margem_fco").name == "ocf_margin"
        assert resolve_metric("ocf_margem").name == "ocf_margin"
        assert resolve_metric("margem_operacional_caixa").name == "ocf_margin"
        assert METRICS["ocf_margin"].engines == ["operating_cf", "revenue"]
