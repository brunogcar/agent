"""Tests for skills/cvm/comparison/ — growth mode + _pct_change helper.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers:
  - growth mode end-to-end (basic shape, QoQ/YoY computation, TTM ratios)
  - validation (missing tickers, < 2 tickers)
  - the _pct_change helper (positive/negative growth, zero/negative base,
    sign-change guards, extreme same-sign growth)

The synthetic FIN_QUARTERLY_SUZB3 fixture lives in conftest.py.
"""
from __future__ import annotations

import pytest

from skills.cvm.comparison import comparison
from tests.skills.cvm.comparison.conftest import FIN_QUARTERLY_SUZB3


class TestGrowthMode:
    def test_growth_requires_tickers(self):
        r = comparison.growth()
        assert r["status"] == "error"

    def test_growth_requires_min_two(self):
        r = comparison.growth(tickers=["SUZB3"])
        assert r["status"] == "error"

    def test_growth_basic_shape(self, monkeypatch):
        def fake_quarterly(company="", periods=8, consolidado=1):
            if company == "SUZB3":
                return FIN_QUARTERLY_SUZB3
            return {"status": "ok", "company": company, "period_type": "quarterly",
                    "periods": FIN_QUARTERLY_SUZB3["periods"],
                    "ttm": FIN_QUARTERLY_SUZB3["ttm"]}
        monkeypatch.setattr("skills.cvm.financials.financials.quarterly", fake_quarterly)
        r = comparison.growth(tickers=["SUZB3", "KLBN11"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["SUZB3", "KLBN11"]
        assert len(r["sections"]) == 1
        sec = r["sections"][0]
        assert "Receita QoQ" in sec["columns"]
        assert "Receita YoY" in sec["columns"]
        assert "ROE (TTM)" in sec["columns"]
        assert len(sec["rows"]) == 2

    def test_growth_qoq_computation(self, monkeypatch):
        """QoQ = (latest - prior) / |prior|."""
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.financials.quarterly", fake_quarterly)
        r = comparison.growth(tickers=["SUZB3", "VALE3"])
        sec = r["sections"][0]
        qoq_idx = sec["columns"].index("Receita QoQ")
        # latest=1T2025=140, prior=4T2024=130 -> (140-130)/130 = 0.0769...
        assert sec["rows"][0][qoq_idx] == pytest.approx((140 - 130) / 130, rel=1e-3)

    def test_growth_yoy_computation(self, monkeypatch):
        """YoY = (latest - same_q_prior_year) / |same_q_prior_year|."""
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.financials.quarterly", fake_quarterly)
        r = comparison.growth(tickers=["SUZB3", "VALE3"])
        sec = r["sections"][0]
        yoy_idx = sec["columns"].index("Receita YoY")
        # latest=1T2025=140, yoy_prior=1T2024=100 (4 periods back) -> (140-100)/100 = 0.4
        assert sec["rows"][0][yoy_idx] == pytest.approx(0.4, rel=1e-3)

    def test_growth_ttm_ratios(self, monkeypatch):
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.financials.quarterly", fake_quarterly)
        r = comparison.growth(tickers=["SUZB3", "VALE3"])
        sec = r["sections"][0]
        roe_idx = sec["columns"].index("ROE (TTM)")
        assert sec["rows"][0][roe_idx] == 0.15  # from ttm.ratios.roe


class TestPctChange:
    """Pure-Python tests for the _pct_change helper used by growth mode."""

    def test_positive_growth(self):
        assert comparison._pct_change(120, 100) == pytest.approx(0.2)

    def test_negative_growth(self):
        assert comparison._pct_change(80, 100) == pytest.approx(-0.2)

    def test_zero_prev_is_none(self):
        assert comparison._pct_change(100, 0) is None

    def test_negative_prev_is_none(self):
        """Sign-change guard: negative base -> None (can't compute meaningful %)."""
        assert comparison._pct_change(36, -1) is None

    def test_sign_change_profit_to_loss_is_none(self):
        """Profit -> loss sign change: +R$1M -> -R$3M = -400% (noise)."""
        assert comparison._pct_change(-3, 1) is None

    def test_sign_change_loss_to_profit_is_none(self):
        """Loss -> profit sign change: -R$1M -> +R$3M (noise)."""
        assert comparison._pct_change(3, -1) is None

    def test_extreme_growth_is_shown(self):
        """Extreme but same-sign growth is NOT suppressed — LLM can judge."""
        assert comparison._pct_change(700, 100) == pytest.approx(6.0)  # 600%

    def test_none_values(self):
        assert comparison._pct_change(None, 100) is None
        assert comparison._pct_change(100, None) is None

    def test_large_same_sign_growth(self):
        """Large same-sign growth passes through (not noise — just big)."""
        assert comparison._pct_change(600, 100) == pytest.approx(5.0)  # 500%
        assert comparison._pct_change(499, 100) == pytest.approx(3.99)  # 399%
