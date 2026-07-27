"""Tests for skills/cvm/calculations/metrics/lpa.py -- LPA + P/L metric.

Uses mocked engines (price, earnings, shares) — no database needed.
"""
from __future__ import annotations

import pytest
from skills.cvm.calculations.metrics import lpa as lpa_metric


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_PRICES = [
    {"date": "2024-01-15", "close": 35.0},
    {"date": "2024-02-15", "close": 36.0},
    {"date": "2024-03-15", "close": 38.0},
    {"date": "2024-04-15", "close": 37.0},
    {"date": "2024-06-15", "close": 40.0},
]

MOCK_EARNINGS_PERIODS = [
    {"date": "2023-12-31", "ttm": 100e9},
    {"date": "2024-03-31", "ttm": 105e9},  # Q1 2024
    {"date": "2024-06-30", "ttm": 110e9},  # H1 2024
]

MOCK_SHARES_PERIODS = [
    {"date": "2000-01-01", "shares": 13e9},  # constant
]


def _mock_engines(monkeypatch):
    """Mock price + earnings + shares engines for lpa metric tests."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.lpa.price_series",
        lambda ticker, df, dt: list(MOCK_PRICES),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.lpa.ttm_earnings_periods",
        lambda company: list(MOCK_EARNINGS_PERIODS),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.lpa.shares_periods",
        lambda company: list(MOCK_SHARES_PERIODS),
    )


# ── lpa_at() tests (per-share value = earnings / shares) ─────────────────────

class TestLpaAt:
    def test_basic_computation(self, monkeypatch):
        """lpa_at = TTM earnings / shares (per-share value, NOT the ratio)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: 110e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9
        )
        # LPA = 110e9 / 13e9 = 8.461...
        result = lpa_metric.lpa_at("PETR4", "2024-06-15")
        assert result == pytest.approx(110e9 / 13e9, rel=1e-3)

    def test_missing_earnings(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: None
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9
        )
        assert lpa_metric.lpa_at("PETR4", "2024-06-15") is None

    def test_missing_shares(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: 110e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: None
        )
        assert lpa_metric.lpa_at("PETR4", "2024-06-15") is None

    def test_negative_earnings_returns_none(self, monkeypatch):
        """Negative earnings → LPA negative → lpa_at returns the negative value.
        But pe_at should return None (P/L meaningless with negative earnings).
        lpa_at itself returns the value (it's just a per-share number).
        Actually, let's check: lpa_at returns earnings/shares. If earnings < 0,
        LPA < 0. We return it — the caller (pe_at) decides if P/L is meaningful.
        """
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: -50e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9
        )
        # lpa_at returns the negative value (per-share number)
        result = lpa_metric.lpa_at("PETR4", "2024-06-15")
        assert result == pytest.approx(-50e9 / 13e9, rel=1e-3)

    def test_zero_earnings_returns_none(self, monkeypatch):
        """Zero earnings → LPA = 0 → None (meaningless)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: 0
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9
        )
        assert lpa_metric.lpa_at("PETR4", "2024-06-15") is None


# ── pe_at() tests (ratio = price / LPA) ──────────────────────────────────────

class TestPeAt:
    def test_basic_computation(self, monkeypatch):
        """pe_at = price / LPA = price / (earnings / shares)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.price_at", lambda t, d: 38.0
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: 110e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9
        )
        # P/L = 38.0 / (110e9 / 13e9) = 38.0 / 8.461 = 4.490...
        result = lpa_metric.pe_at("PETR4", "2024-06-15")
        assert result == pytest.approx(38.0 / (110e9 / 13e9), rel=1e-3)

    def test_missing_price(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: 110e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9)
        assert lpa_metric.pe_at("PETR4", "2024-06-15") is None

    def test_zero_price_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.price_at", lambda t, d: 0.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: 110e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9)
        assert lpa_metric.pe_at("PETR4", "2024-06-15") is None

    def test_negative_earnings_returns_none(self, monkeypatch):
        """Negative earnings → LPA < 0 → P/L meaningless → None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.ttm_earnings_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.lpa.shares_at", lambda c, d: 13e9)
        assert lpa_metric.pe_at("PETR4", "2024-06-15") is None


# ── lpa_history() tests (series with lpa + pe) ───────────────────────────────

class TestLpaHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = lpa_metric.lpa_history("PETR4", "2024-01-01", "2024-06-30")
        assert len(result) == 5
        for entry in result:
            assert "date" in entry
            assert "price" in entry
            assert "ttm_earnings" in entry
            assert "shares" in entry
            assert "lpa" in entry   # per-share value
            assert "pe" in entry    # price ratio

    def test_step_function_earnings_lookup(self, monkeypatch):
        """TTM earnings should be the most recent period <= date."""
        _mock_engines(monkeypatch)
        result = lpa_metric.lpa_history("PETR4", "2024-01-01", "2024-06-30")
        # 2024-01-15 → most recent earnings <= 2024-01-15 is 2023-12-31 (100e9)
        assert result[0]["ttm_earnings"] == 100e9
        assert result[0]["lpa"] == pytest.approx(100e9 / 13e9, rel=1e-3)
        assert result[0]["pe"] == pytest.approx(35.0 / (100e9 / 13e9), rel=1e-3)
        # 2024-04-15 → most recent earnings is 2024-03-31 (105e9)
        assert result[3]["ttm_earnings"] == 105e9

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.price_series",
            lambda t, df, dt: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_periods",
            lambda c: list(MOCK_EARNINGS_PERIODS),
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        assert lpa_metric.lpa_history("PETR4", "2024-01-01", "2024-06-30") == []

    def test_no_earnings_before_date_yields_none(self, monkeypatch):
        """If no earnings period <= date, lpa and pe should be None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.price_series",
            lambda t, df, dt: [{"date": "2020-01-15", "close": 30.0}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.ttm_earnings_periods",
            lambda c: [{"date": "2023-12-31", "ttm": 100e9}],  # all after 2020
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.lpa.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        result = lpa_metric.lpa_history("PETR4", "2020-01-01", "2020-02-01")
        assert len(result) == 1
        assert result[0]["lpa"] is None
        assert result[0]["pe"] is None
        assert result[0]["ttm_earnings"] is None


# ── Metric registry test ────────────────────────────────────────────────────

class TestMetricRegistry:
    def test_lpa_registered(self):
        from skills.cvm.calculations._registry import METRICS
        assert "lpa" in METRICS
        assert METRICS["lpa"].ratio_key == "pe"
        assert METRICS["lpa"].per_share_key == "lpa"

    def test_lpa_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("pe").name == "lpa"
        assert resolve_metric("pl").name == "lpa"
        assert resolve_metric("p/l").name == "lpa"
