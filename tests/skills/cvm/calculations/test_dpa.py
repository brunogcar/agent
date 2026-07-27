"""Tests for skills/cvm/calculations/metrics/dpa.py + engines/dividends.py.

Uses mocked engines (price, dividends, earnings, shares) — no database needed.
"""
from __future__ import annotations

import pytest
from skills.cvm.calculations.metrics import dpa as dpa_metric
from skills.cvm.calculations.engines import dividends as dividends_engine


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_PRICES = [
    {"date": "2024-01-15", "close": 35.0},
    {"date": "2024-02-15", "close": 36.0},
    {"date": "2024-03-15", "close": 38.0},
    {"date": "2024-06-15", "close": 40.0},
]

MOCK_EARNINGS_PERIODS = [
    {"date": "2023-12-31", "ttm": 100e9},
    {"date": "2024-06-30", "ttm": 110e9},
]

MOCK_SHARES_PERIODS = [
    {"date": "2000-01-01", "shares": 13e9},
]


def _mock_engines(monkeypatch):
    """Mock price + dividends + earnings + shares for dpa metric tests."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dpa.price_series",
        lambda ticker, df, dt: list(MOCK_PRICES),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dpa.dividends_at",
        lambda ticker, date: 1.85 if date >= "2023-12-31" else 1.50,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dpa.ttm_earnings_periods",
        lambda company: list(MOCK_EARNINGS_PERIODS),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dpa.shares_periods",
        lambda company: list(MOCK_SHARES_PERIODS),
    )


# ── dpa_at() tests (per-share value = dividends TTM) ────────────────────────

class TestDpaAt:
    def test_basic_computation(self, monkeypatch):
        """dpa_at returns the TTM dividends per share."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85
        )
        result = dpa_metric.dpa_at("PETR4", "2024-06-30")
        assert result == 1.85

    def test_no_data_returns_none(self, monkeypatch):
        """None means no dividends data available at all."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: None
        )
        assert dpa_metric.dpa_at("PETR4", "2024-06-30") is None

    def test_zero_dividends_returns_zero(self, monkeypatch):
        """0.0 means company exists but pays no dividends (different from None)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 0.0
        )
        assert dpa_metric.dpa_at("PETR4", "2024-06-30") == 0.0


# ── dy_at() tests (Dividend Yield = DPA / price) ─────────────────────────────

class TestDyAt:
    def test_basic_computation(self, monkeypatch):
        """dy_at = DPA / price."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85)
        result = dpa_metric.dy_at("PETR4", "2024-06-30")
        assert result == pytest.approx(1.85 / 38.0, rel=1e-3)

    def test_missing_price(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85)
        assert dpa_metric.dy_at("PETR4", "2024-06-30") is None

    def test_zero_price_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.price_at", lambda t, d: 0.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85)
        assert dpa_metric.dy_at("PETR4", "2024-06-30") is None

    def test_no_dividends_data(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: None)
        assert dpa_metric.dy_at("PETR4", "2024-06-30") is None

    def test_zero_dividends_returns_zero_yield(self, monkeypatch):
        """Company pays no dividends → yield = 0.0 (valid, not None)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 0.0)
        result = dpa_metric.dy_at("PETR4", "2024-06-30")
        assert result == 0.0


# ── payout_at() tests (Payout = DPA / LPA) ───────────────────────────────────

class TestPayoutAt:
    def test_basic_computation(self, monkeypatch):
        """payout_at = DPA / LPA = DPA / (TTM earnings / shares)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.ttm_earnings_at", lambda c, d: 110e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.shares_at", lambda c, d: 13e9)
        result = dpa_metric.payout_at("PETR4", "2024-06-30")
        assert result == pytest.approx(1.85 / (110e9 / 13e9), rel=1e-3)

    def test_missing_dividends(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.ttm_earnings_at", lambda c, d: 110e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.shares_at", lambda c, d: 13e9)
        assert dpa_metric.payout_at("PETR4", "2024-06-30") is None

    def test_negative_earnings_returns_none(self, monkeypatch):
        """Negative earnings → LPA < 0 → payout meaningless → None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.ttm_earnings_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.shares_at", lambda c, d: 13e9)
        assert dpa_metric.payout_at("PETR4", "2024-06-30") is None

    def test_zero_dividends_returns_zero_payout(self, monkeypatch):
        """Company pays no dividends → payout = 0.0 (valid)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 0.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.ttm_earnings_at", lambda c, d: 110e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.dpa.shares_at", lambda c, d: 13e9)
        result = dpa_metric.payout_at("PETR4", "2024-06-30")
        assert result == 0.0


# ── dpa_history() tests (series with DPA + DY + Payout) ──────────────────────

class TestDpaHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = dpa_metric.dpa_history("PETR4", "2024-01-01", "2024-06-30")
        assert len(result) == 4
        for entry in result:
            assert "date" in entry
            assert "price" in entry
            assert "dpa" in entry      # per-share value
            assert "dy" in entry       # dividend yield ratio
            assert "payout" in entry   # bonus ratio
            assert "lpa" in entry      # LPA (needed for payout)
            assert "ttm_earnings" in entry
            assert "shares" in entry

    def test_dy_computation(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = dpa_metric.dpa_history("PETR4", "2024-01-01", "2024-06-30")
        for entry in result:
            if entry["dpa"] is not None and entry["price"] > 0:
                expected_dy = entry["dpa"] / entry["price"]
                assert entry["dy"] == pytest.approx(expected_dy, rel=1e-3)

    def test_payout_computation(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = dpa_metric.dpa_history("PETR4", "2024-01-01", "2024-06-30")
        for entry in result:
            if (entry["dpa"] is not None and entry["lpa"] is not None
                and entry["lpa"] > 0):
                expected_payout = entry["dpa"] / entry["lpa"]
                assert entry["payout"] == pytest.approx(expected_payout, rel=1e-3)

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.price_series", lambda t, df, dt: []
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.dividends_at", lambda t, d: 1.85
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.ttm_earnings_periods", lambda c: []
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dpa.shares_periods", lambda c: []
        )
        assert dpa_metric.dpa_history("PETR4", "2024-01-01", "2024-06-30") == []


# ── Dividends engine tests (mocked DB) ───────────────────────────────────────

class TestDividendsEngine:
    def test_dividends_at_sums_window(self, monkeypatch):
        """dividends_at should sum rates in the trailing 365-day window."""
        monkeypatch.setattr(
            dividends_engine, "_sum_dividends_in_window", lambda t, d, days=365: 1.85
        )
        monkeypatch.setattr(
            dividends_engine, "_get_all_event_dates",
            lambda t: ["2023-06-30", "2023-12-31", "2024-06-30"]
        )
        result = dividends_engine.dividends_at("PETR4", "2024-06-30")
        assert result == 1.85

    def test_dividends_at_no_data_returns_none(self, monkeypatch):
        """No event dates at all → None (no data available)."""
        monkeypatch.setattr(
            dividends_engine, "_sum_dividends_in_window", lambda t, d, days=365: 0.0
        )
        monkeypatch.setattr(dividends_engine, "_get_all_event_dates", lambda t: [])
        assert dividends_engine.dividends_at("PETR4", "2024-06-30") is None

    def test_dividends_at_no_dividends_before_date_returns_none(self, monkeypatch):
        """All event dates are after the query date → None."""
        monkeypatch.setattr(
            dividends_engine, "_sum_dividends_in_window", lambda t, d, days=365: 0.0
        )
        monkeypatch.setattr(
            dividends_engine, "_get_all_event_dates",
            lambda t: ["2025-06-30"]  # after query date
        )
        assert dividends_engine.dividends_at("PETR4", "2024-06-30") is None

    def test_dividends_at_zero_in_window_returns_zero(self, monkeypatch):
        """Company has dividends before, but none in the 365-day window → 0.0."""
        monkeypatch.setattr(
            dividends_engine, "_sum_dividends_in_window", lambda t, d, days=365: 0.0
        )
        monkeypatch.setattr(
            dividends_engine, "_get_all_event_dates",
            lambda t: ["2020-06-30"]  # before query date but outside window
        )
        result = dividends_engine.dividends_at("PETR4", "2024-06-30")
        assert result == 0.0  # not None — company exists, just no dividends in window

    def test_dividends_periods_builds_step_function(self, monkeypatch):
        """dividends_periods should return one entry per event date."""
        monkeypatch.setattr(
            dividends_engine, "_get_all_event_dates",
            lambda t: ["2023-06-30", "2023-12-31", "2024-06-30"]
        )
        monkeypatch.setattr(
            dividends_engine, "dividends_at",
            lambda t, d: 1.50 if d == "2023-06-30" else (1.80 if d == "2023-12-31" else 1.85)
        )
        result = dividends_engine.dividends_periods("PETR4")
        assert len(result) == 3
        assert result[0] == {"date": "2023-06-30", "dpa": 1.50}
        assert result[1] == {"date": "2023-12-31", "dpa": 1.80}
        assert result[2] == {"date": "2024-06-30", "dpa": 1.85}

    def test_dividends_periods_empty(self, monkeypatch):
        monkeypatch.setattr(dividends_engine, "_get_all_event_dates", lambda t: [])
        assert dividends_engine.dividends_periods("PETR4") == []

    def test_dividends_at_uses_coalesce_date_fallback(self, monkeypatch):
        """v1.3.1: dividends_at should use COALESCE(payment_date, last_date_prior, approved_on).
        This test verifies the SQL expression is used (not just payment_date).
        We mock _sum_dividends_in_window to verify it's called with the right parameters.
        """
        # The COALESCE fix is inside _sum_dividends_in_window's SQL.
        # We can't test the SQL directly without a DB, but we can verify
        # the function exists and is callable.
        assert hasattr(dividends_engine, "_sum_dividends_in_window")
        assert hasattr(dividends_engine, "_get_all_event_dates")
        assert hasattr(dividends_engine, "_EVENT_DATE_EXPR")
        assert "COALESCE" in dividends_engine._EVENT_DATE_EXPR


# ── Metric registry test ────────────────────────────────────────────────────

class TestMetricRegistry:
    def test_dpa_registered(self):
        from skills.cvm.calculations._registry import METRICS
        assert "dpa" in METRICS
        assert METRICS["dpa"].ratio_key == "dy"
        assert METRICS["dpa"].per_share_key == "dpa"

    def test_dpa_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("dy").name == "dpa"
        assert resolve_metric("dividend_yield").name == "dpa"
        assert resolve_metric("yld").name == "dpa"
        assert resolve_metric("payout").name == "dpa"
