"""Tests for skills/cvm/historical/metrics/vpa.py + engines/pl.py.

Uses mocked engines (price, pl, shares) — no database needed.
"""
from __future__ import annotations

import pytest
from skills.cvm.historical.metrics import vpa as vpa_metric
from skills.cvm.historical.engines import pl as pl_engine


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_PRICES = [
    {"date": "2024-01-15", "close": 35.0},
    {"date": "2024-02-15", "close": 36.0},
    {"date": "2024-03-15", "close": 38.0},
    {"date": "2024-04-15", "close": 37.0},
    {"date": "2024-06-15", "close": 40.0},
]

MOCK_PL_PERIODS = [
    {"date": "2023-12-31", "pl": 290e9},
    {"date": "2024-03-31", "pl": 300e9},  # Q1 2024 snapshot
    {"date": "2024-06-30", "pl": 310e9},  # H1 2024 snapshot
]

MOCK_SHARES_PERIODS = [
    {"date": "2000-01-01", "shares": 13e9},  # constant (investsite fallback)
]


def _mock_engines(monkeypatch):
    """Mock price + pl + shares engines for vpa metric tests."""
    monkeypatch.setattr(
        "skills.cvm.historical.metrics.vpa.price_series",
        lambda ticker, df, dt: list(MOCK_PRICES),
    )
    monkeypatch.setattr(
        "skills.cvm.historical.metrics.vpa.pl_periods",
        lambda company: list(MOCK_PL_PERIODS),
    )
    monkeypatch.setattr(
        "skills.cvm.historical.metrics.vpa.shares_periods",
        lambda company: list(MOCK_SHARES_PERIODS),
    )


# ── vpa_at() tests (per-share value = PL / shares) ──────────────────────────

class TestVpaAt:
    def test_basic_computation(self, monkeypatch):
        """vpa_at = PL / shares (per-share value, NOT the ratio)."""
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: 310e9
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9
        )
        # VPA = 310e9 / 13e9 = 23.846...
        result = vpa_metric.vpa_at("PETR4", "2024-06-15")
        assert result == pytest.approx(310e9 / 13e9, rel=1e-3)

    def test_missing_pl(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.vpa_at("PETR4", "2024-06-15") is None

    def test_missing_shares(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: 310e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: None)
        assert vpa_metric.vpa_at("PETR4", "2024-06-15") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity → VPA meaningless → None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.vpa_at("PETR4", "2024-06-15") is None


# ── pvpa_at() tests (ratio = price / VPA) ────────────────────────────────────

class TestPvpaAt:
    def test_basic_computation(self, monkeypatch):
        """pvpa_at = price / VPA = price / (PL / shares)."""
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.price_at", lambda t, d: 38.0
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: 310e9
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9
        )
        # P/VPA = 38.0 / (310e9 / 13e9) = 38.0 / 23.846 = 1.5935...
        result = vpa_metric.pvpa_at("PETR4", "2024-06-15")
        assert result == pytest.approx(38.0 / (310e9 / 13e9), rel=1e-3)

    def test_missing_price(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.price_at", lambda t, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: 310e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.pvpa_at("PETR4", "2024-06-15") is None

    def test_zero_price_returns_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.price_at", lambda t, d: 0.0)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: 310e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.pvpa_at("PETR4", "2024-06-15") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity → P/VPA meaningless → None."""
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.price_at", lambda t, d: 38.0)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.pl_at", lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.vpa.shares_at", lambda c, d: 13e9)
        assert vpa_metric.pvpa_at("PETR4", "2024-06-15") is None


# ── vpa_history() tests (series with vpa + pvpa) ─────────────────────────────

class TestVpaHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_engines(monkeypatch)
        result = vpa_metric.vpa_history("PETR4", "2024-01-01", "2024-06-30")
        assert len(result) == 5
        for entry in result:
            assert "date" in entry
            assert "price" in entry
            assert "pl" in entry
            assert "shares" in entry
            assert "vpa" in entry     # per-share value
            assert "pvpa" in entry    # price ratio

    def test_step_function_pl_lookup(self, monkeypatch):
        """PL should be the most recent snapshot <= date."""
        _mock_engines(monkeypatch)
        result = vpa_metric.vpa_history("PETR4", "2024-01-01", "2024-06-30")
        # 2024-01-15 → most recent PL snapshot <= 2024-01-15 is 2023-12-31 (290e9)
        assert result[0]["pl"] == 290e9
        assert result[0]["vpa"] == pytest.approx(290e9 / 13e9, rel=1e-3)
        assert result[0]["pvpa"] == pytest.approx(35.0 / (290e9 / 13e9), rel=1e-3)
        # 2024-04-15 → most recent PL is 2024-03-31 (300e9)
        assert result[3]["pl"] == 300e9
        # 2024-06-15 → most recent PL is 2024-03-31 (300e9), NOT 2024-06-30 (after)
        assert result[4]["pl"] == 300e9

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.price_series",
            lambda t, df, dt: [],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.pl_periods",
            lambda c: list(MOCK_PL_PERIODS),
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        assert vpa_metric.vpa_history("PETR4", "2024-01-01", "2024-06-30") == []

    def test_no_pl_before_date_yields_none_vpa(self, monkeypatch):
        """If no PL snapshot <= date, vpa and pvpa should be None."""
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.price_series",
            lambda t, df, dt: [{"date": "2020-01-15", "close": 30.0}],
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.pl_periods",
            lambda c: [{"date": "2023-12-31", "pl": 290e9}],  # all after 2020-01-15
        )
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.shares_periods",
            lambda c: list(MOCK_SHARES_PERIODS),
        )
        result = vpa_metric.vpa_history("PETR4", "2020-01-01", "2020-02-01")
        assert len(result) == 1
        assert result[0]["vpa"] is None
        assert result[0]["pvpa"] is None
        assert result[0]["pl"] is None


# ── PL engine tests (mocked DB) ──────────────────────────────────────────────

class TestPlEngine:
    def test_pl_at_finds_most_recent_snapshot(self, monkeypatch):
        """pl_at should return the most recent PL snapshot <= date."""
        fake_dfp = {"2023-12-31": {"value": 290e9, "year": 2023}}
        fake_itr = {
            "2024-03-31": {"value": 300e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 310e9, "meses": 6, "year": 2024},
        }
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)

        assert pl_engine.pl_at("PETR4", "2024-04-15") == 300e9
        assert pl_engine.pl_at("PETR4", "2024-07-01") == 310e9
        assert pl_engine.pl_at("PETR4", "2023-12-31") == 290e9

    def test_pl_at_no_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: {})
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: {})
        assert pl_engine.pl_at("PETR4", "2024-06-30") is None

    def test_pl_at_no_snapshot_before_date(self, monkeypatch):
        """If all snapshots are after date, return None."""
        fake_dfp = {"2024-12-31": {"value": 380e9, "year": 2024}}
        fake_itr = {}
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)
        assert pl_engine.pl_at("PETR4", "2024-06-30") is None

    def test_pl_periods_merges_dfp_and_itr(self, monkeypatch):
        """pl_periods should merge DFP + ITR snapshots, sorted oldest-first."""
        fake_dfp = {
            "2023-12-31": {"value": 290e9, "year": 2023},
            "2024-12-31": {"value": 380e9, "year": 2024},
        }
        fake_itr = {
            "2024-03-31": {"value": 300e9, "meses": 3, "year": 2024},
            "2024-06-30": {"value": 310e9, "meses": 6, "year": 2024},
            "2024-09-30": {"value": 330e9, "meses": 9, "year": 2024},
        }
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)

        result = pl_engine.pl_periods("PETR4")
        assert len(result) == 5
        assert result[0] == {"date": "2023-12-31", "pl": 290e9}
        assert result[4] == {"date": "2024-12-31", "pl": 380e9}

    def test_pl_periods_dedupes_same_date(self, monkeypatch):
        fake_dfp = {"2024-12-31": {"value": 380e9, "year": 2024}}
        fake_itr = {"2024-12-31": {"value": 380e9, "meses": 9, "year": 2024}}
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: fake_dfp)
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: fake_itr)

        result = pl_engine.pl_periods("PETR4")
        assert len(result) == 1

    def test_pl_periods_empty(self, monkeypatch):
        monkeypatch.setattr(pl_engine, "_get_dfp_pl", lambda c: {})
        monkeypatch.setattr(pl_engine, "_get_itr_pl", lambda c: {})
        assert pl_engine.pl_periods("PETR4") == []


# ── Metric registry test ────────────────────────────────────────────────────

class TestMetricRegistry:
    def test_vpa_registered(self):
        from skills.cvm.historical.metrics._registry import METRICS
        assert "vpa" in METRICS
        assert METRICS["vpa"].ratio_key == "pvpa"
        assert METRICS["vpa"].per_share_key == "vpa"

    def test_vpa_aliases_include_pvpa(self):
        from skills.cvm.historical.metrics._registry import resolve_metric
        assert resolve_metric("pvpa").name == "vpa"
        assert resolve_metric("p/vpa").name == "vpa"
