"""Tests for skills/cvm/calculations/metrics/rps.py + engines/revenue.py.

Uses mocked engines (price, revenue, shares) -- no database needed.
Mirrors test_lpa.py structure since RPS/PSR follows the same pattern as
LPA/P/L (per-share value + price ratio, step-function optimization).
"""
from __future__ import annotations

import pytest
from skills.cvm.calculations.metrics import rps as rps_metric
from skills.cvm.calculations.engines.dre import revenue as revenue_engine


# -- Mock data ---------------------------------------------------------------

MOCK_PRICES = [
    {"date": "2024-01-15", "close": 35.0},
    {"date": "2024-02-15", "close": 36.0},
    {"date": "2024-03-15", "close": 38.0},
    {"date": "2024-04-15", "close": 37.0},
    {"date": "2024-06-15", "close": 40.0},
]

MOCK_REVENUE_PERIODS = [
    {"date": "2023-12-31", "ttm_rev": 250e9},
    {"date": "2024-03-31", "ttm_rev": 260e9},  # Q1 2024
    {"date": "2024-06-30", "ttm_rev": 280e9},  # H1 2024
]

MOCK_SHARES_PERIODS = [
    {"date": "2000-01-01", "shares": 13e9},  # constant
]


def _mock_engines(monkeypatch):
    """Mock price + revenue + shares engines for rps metric tests."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.rps.price_series",
        lambda ticker, df, dt: list(MOCK_PRICES),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.rps.revenue_periods",
        lambda company: list(MOCK_REVENUE_PERIODS),
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.rps.shares_periods",
        lambda company: list(MOCK_SHARES_PERIODS),
    )


# -- rps_at() tests (per-share value = revenue / shares) ---------------------

class TestRpsAt:
    def test_basic_computation(self, monkeypatch):
        """rps_at = TTM revenue / shares (per-share value, NOT the ratio)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 280e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9
        )
        # RPS = 280e9 / 13e9 = 21.538...
        result = rps_metric.rps_at("PETR4", "2024-06-15")
        assert result == pytest.approx(280e9 / 13e9, rel=1e-3)

    def test_missing_revenue(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: None
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9
        )
        assert rps_metric.rps_at("PETR4", "2024-06-15") is None

    def test_missing_shares(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 280e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: None
        )
        assert rps_metric.rps_at("PETR4", "2024-06-15") is None

    def test_zero_revenue_returns_none(self, monkeypatch):
        """Zero revenue -> RPS = 0 -> None (meaningless)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 0
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9
        )
        assert rps_metric.rps_at("PETR4", "2024-06-15") is None


# -- psr_at() tests (ratio = price / RPS) -------------------------------------

class TestPsrAt:
    def test_basic_computation(self, monkeypatch):
        """psr_at = price / RPS = price / (revenue / shares)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.price_at", lambda t, d: 38.0
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 280e9
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9
        )
        # PSR = 38.0 / (280e9 / 13e9) = 38.0 / 21.538 = 1.763...
        result = rps_metric.psr_at("PETR4", "2024-06-15")
        assert result == pytest.approx(38.0 / (280e9 / 13e9), rel=1e-3)

    def test_missing_price(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9)
        assert rps_metric.psr_at("PETR4", "2024-06-15") is None

    def test_zero_price_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.price_at", lambda t, d: 0.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9)
        assert rps_metric.psr_at("PETR4", "2024-06-15") is None

    def test_zero_revenue_returns_none(self, monkeypatch):
        """No revenue -> RPS = None -> PSR meaningless -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.revenue_at", lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.rps.shares_at", lambda c, d: 13e9)
        assert rps_metric.psr_at("PETR4", "2024-06-15") is None


# -- rps_history() tests (series with RPS + PSR) ------------------------------

class TestRpsHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = rps_metric.rps_history("PETR4", "2024-01-01", "2024-06-30")
        assert len(result) == 5
        for entry in result:
            assert "date" in entry
            assert "price" in entry
            assert "ttm_rev" in entry
            assert "shares" in entry
            assert "rps" in entry   # per-share value
            assert "psr" in entry   # price ratio

    def test_step_function_revenue_lookup(self, monkeypatch):
        """TTM revenue should be the most recent period <= date."""
        _mock_engines(monkeypatch)
        result = rps_metric.rps_history("PETR4", "2024-01-01", "2024-06-30")
        # 2024-01-15 -> most recent revenue <= 2024-01-15 is 2023-12-31 (250e9)
        assert result[0]["ttm_rev"] == 250e9
        assert result[0]["rps"] == pytest.approx(250e9 / 13e9, rel=1e-3)
        assert result[0]["psr"] == pytest.approx(35.0 / (250e9 / 13e9), rel=1e-3)
        # 2024-04-15 -> most recent revenue is 2024-03-31 (260e9)
        assert result[3]["ttm_rev"] == 260e9

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.price_series",
            lambda t, df, dt: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_periods",
            lambda c: list(MOCK_REVENUE_PERIODS),
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        assert rps_metric.rps_history("PETR4", "2024-01-01", "2024-06-30") == []

    def test_no_revenue_before_date_yields_none(self, monkeypatch):
        """If no revenue period <= date, rps and psr should be None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.price_series",
            lambda t, df, dt: [{"date": "2020-01-15", "close": 30.0}],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.revenue_periods",
            lambda c: [{"date": "2023-12-31", "ttm_rev": 250e9}],  # all after 2020
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.rps.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        result = rps_metric.rps_history("PETR4", "2020-01-01", "2020-02-01")
        assert len(result) == 1
        assert result[0]["rps"] is None
        assert result[0]["psr"] is None
        assert result[0]["ttm_rev"] is None


# -- Revenue engine tests (mocked DB) -----------------------------------------

class TestRevenueEngine:
    def test_revenue_at_finds_most_recent_ttm(self, monkeypatch):
        """revenue_at should derive TTM revenue at any date via DFP + ITR."""
        fake_dfp = {"2023": {"value": 250e9, "date": "2023-12-31"}}
        fake_itr = {
            "2024-03-31": {"value": 60e9, "meses": 3, "year": 2024},
            "2023-03-31": {"value": 55e9, "meses": 3, "year": 2023},
        }
        monkeypatch.setattr(revenue_engine, "_get_dfp_revenue", lambda c: fake_dfp)
        monkeypatch.setattr(revenue_engine, "_get_itr_revenue", lambda c: fake_itr)

        # TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
        # = 250e9 - 55e9 + 60e9 = 255e9
        result = revenue_engine.revenue_at("PETR4", "2024-04-15")
        assert result == 255e9

    def test_revenue_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(revenue_engine, "_get_dfp_revenue", lambda c: {})
        monkeypatch.setattr(revenue_engine, "_get_itr_revenue", lambda c: {})
        assert revenue_engine.revenue_at("PETR4", "2024-06-30") is None

    def test_revenue_at_no_itr_before_date_uses_dfp(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2023": {"value": 250e9, "date": "2023-12-31"}}
        fake_itr = {}  # no ITR data
        monkeypatch.setattr(revenue_engine, "_get_dfp_revenue", lambda c: fake_dfp)
        monkeypatch.setattr(revenue_engine, "_get_itr_revenue", lambda c: fake_itr)
        assert revenue_engine.revenue_at("PETR4", "2024-01-15") == 250e9

    def test_revenue_periods_builds_step_function(self, monkeypatch):
        """revenue_periods should return one entry per ITR period with TTM."""
        fake_dfp = {"2023": {"value": 250e9, "date": "2023-12-31"}}
        fake_itr = {
            "2024-03-31": {"value": 60e9, "meses": 3, "year": 2024},
            "2023-03-31": {"value": 55e9, "meses": 3, "year": 2023},
        }
        monkeypatch.setattr(revenue_engine, "_get_dfp_revenue", lambda c: fake_dfp)
        monkeypatch.setattr(revenue_engine, "_get_itr_revenue", lambda c: fake_itr)

        result = revenue_engine.revenue_periods("PETR4")
        # Should have entries for 2023-03-31, 2023-12-31 (DFP-only), 2024-03-31
        assert len(result) >= 1
        # All entries should have ttm_rev key
        for p in result:
            assert "date" in p
            assert "ttm_rev" in p

    def test_revenue_periods_empty(self, monkeypatch):
        monkeypatch.setattr(revenue_engine, "_get_dfp_revenue", lambda c: {})
        monkeypatch.setattr(revenue_engine, "_get_itr_revenue", lambda c: {})
        assert revenue_engine.revenue_periods("PETR4") == []

    def test_revenue_uses_codigo_3_01(self, monkeypatch):
        """Revenue engine should query DRE codigo 3.01 (Receita Liquida)."""
        assert revenue_engine.RECEITA_LIQUIDA_CODE == "3.01"

    def test_revenue_engine_registered(self):
        """Revenue engine should be auto-discovered and registered."""
        from skills.cvm.calculations._registry import ENGINES
        assert "revenue" in ENGINES
        assert ENGINES["revenue"].quantity == "ttm_rev"
        assert "3.01" in ENGINES["revenue"].source or "Receita" in ENGINES["revenue"].source


# -- Metric registry test ----------------------------------------------------

class TestMetricRegistry:
    def test_rps_registered(self):
        from skills.cvm.calculations._registry import METRICS
        assert "rps" in METRICS
        assert METRICS["rps"].ratio_key == "psr"
        assert METRICS["rps"].per_share_key == "rps"
        assert METRICS["rps"].per_share_label == "RPS"
        assert METRICS["rps"].ratio_label == "PSR"

    def test_rps_aliases(self):
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("psr").name == "rps"
        assert resolve_metric("p/sr").name == "rps"
        assert resolve_metric("price_sales").name == "rps"
