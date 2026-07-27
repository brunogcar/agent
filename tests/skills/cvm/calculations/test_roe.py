"""Tests for skills/cvm/calculations/metrics/roe.py -- ROE fundamental ratio.

Uses mocked engines (earnings, pl) -- no database needed.
ROE is the first fundamental ratio (no price, no shares, per_share=None).
"""
from __future__ import annotations

import pytest
from skills.cvm.calculations.metrics import roe as roe_metric


# -- Mock data ---------------------------------------------------------------

MOCK_EARNINGS_PERIODS = [
    {"date": "2023-12-31", "ttm": 100e9},
    {"date": "2024-03-31", "ttm": 110e9},
    {"date": "2024-06-30", "ttm": 120e9},
]

MOCK_PL_PERIODS = [
    {"date": "2023-12-31", "pl": 300e9},
    {"date": "2024-03-31", "pl": 320e9},
    {"date": "2024-06-30", "pl": 350e9},
]


def _mock_engines(monkeypatch):
    """Mock earnings + pl engines for roe metric tests."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.roe.ttm_earnings_periods",
        lambda company: list(MOCK_EARNINGS_PERIODS),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.roe.pl_periods",
        lambda company: list(MOCK_PL_PERIODS),
    )


# -- roe_at() tests (ratio = earnings / PL) ----------------------------------

class TestRoeAt:
    def test_basic_computation(self, monkeypatch):
        """roe_at = TTM earnings / PL."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: 120e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: 350e9
        )
        # ROE = 120e9 / 350e9 = 0.3428...
        result = roe_metric.roe_at("PETR4", "2024-06-30")
        assert result == pytest.approx(120e9 / 350e9, rel=1e-3)

    def test_missing_earnings(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: None
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: 350e9
        )
        assert roe_metric.roe_at("PETR4", "2024-06-30") is None

    def test_missing_pl(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: 120e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: None
        )
        assert roe_metric.roe_at("PETR4", "2024-06-30") is None

    def test_negative_earnings_returns_none(self, monkeypatch):
        """Negative earnings -> ROE meaningless -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: -50e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: 350e9
        )
        assert roe_metric.roe_at("PETR4", "2024-06-30") is None

    def test_zero_earnings_returns_none(self, monkeypatch):
        """Zero earnings -> ROE = 0 -> None (meaningless)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: 0
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: 350e9
        )
        assert roe_metric.roe_at("PETR4", "2024-06-30") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity -> ROE meaningless -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: 120e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: -50e9
        )
        assert roe_metric.roe_at("PETR4", "2024-06-30") is None

    def test_zero_pl_returns_none(self, monkeypatch):
        """Zero PL -> division by zero -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_at", lambda c, d: 120e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_at", lambda c, d: 0
        )
        assert roe_metric.roe_at("PETR4", "2024-06-30") is None


# -- roe_history() tests (series with ROE, no price) -------------------------

class TestRoeHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = roe_metric.roe_history("PETR4", "2023-01-01", "2024-12-31")
        assert len(result) >= 3  # at least the 3 period dates
        for entry in result:
            assert "date" in entry
            assert "roe" in entry       # the ratio
            assert "ttm_earnings" in entry
            assert "pl" in entry
            # Fundamental ratio -- NO price, NO shares, NO per-share value
            assert "price" not in entry
            assert "shares" not in entry

    def test_roe_computation(self, monkeypatch):
        """ROE should be earnings / PL at each date."""
        _mock_engines(monkeypatch)
        result = roe_metric.roe_history("PETR4", "2023-01-01", "2024-12-31")
        for entry in result:
            if (entry["ttm_earnings"] is not None and entry["ttm_earnings"] > 0
                and entry["pl"] is not None and entry["pl"] > 0):
                expected_roe = entry["ttm_earnings"] / entry["pl"]
                assert entry["roe"] == pytest.approx(expected_roe, rel=1e-3)
            else:
                assert entry["roe"] is None

    def test_empty_periods_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.ttm_earnings_periods", lambda c: []
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.roe.pl_periods", lambda c: []
        )
        assert roe_metric.roe_history("PETR4", "2024-01-01", "2024-12-31") == []

    def test_date_range_filter(self, monkeypatch):
        """Only dates within [date_from, date_to] should be included."""
        _mock_engines(monkeypatch)
        # Narrow range that excludes 2023-12-31
        result = roe_metric.roe_history("PETR4", "2024-01-01", "2024-12-31")
        for entry in result:
            assert entry["date"] >= "2024-01-01"
            assert entry["date"] <= "2024-12-31"

    def test_no_price_in_series(self, monkeypatch):
        """Fundamental ratio -- series should NOT have a 'price' key."""
        _mock_engines(monkeypatch)
        result = roe_metric.roe_history("PETR4", "2024-01-01", "2024-12-31")
        for entry in result:
            assert "price" not in entry


# -- Metric registry test ----------------------------------------------------

class TestMetricRegistry:
    def test_roe_registered(self):
        from skills.cvm.calculations._registry import METRICS
        assert "roe" in METRICS
        spec = METRICS["roe"]
        assert spec.ratio_key == "roe"
        assert spec.ratio_label == "ROE"
        # Fundamental ratio -- no per-share value
        assert spec.per_share_key is None
        assert spec.per_share_label is None
        assert spec.per_share_fn is None

    def test_roe_engines(self):
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["roe"]
        assert "earnings" in spec.engines
        assert "pl" in spec.engines
        # Should NOT include price or shares
        assert "price" not in spec.engines
        assert "shares" not in spec.engines

    def test_roe_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("return_on_equity").name == "roe"
        assert resolve_metric("roe").name == "roe"
