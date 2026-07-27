"""Tests for backtest run mode + strategies mode."""
from __future__ import annotations

import pytest
from skills.cvm.backtest.backtest import (
    run, strategies, BUILTIN_STRATEGIES,
    _precompute_signals, _lookup_signal,
)


# ── Strategies mode ──────────────────────────────────────────────────────────

class TestStrategiesMode:
    def test_lists_all_strategies(self):
        r = strategies()
        assert r["status"] == "ok"
        assert r["count"] == 6
        names = [s["name"] for s in r["strategies"]]
        assert set(names) == {"value_pe", "value_pvpa", "quality_roe",
                              "quality_roic", "income_dy", "composite"}

    def test_each_strategy_has_description(self):
        r = strategies()
        for s in r["strategies"]:
            assert "description" in s
            assert len(s["description"]) > 10

    def test_each_strategy_has_metrics(self):
        r = strategies()
        for s in r["strategies"]:
            assert "metrics" in s
            assert len(s["metrics"]) >= 1

    def test_each_strategy_has_max_holding(self):
        r = strategies()
        for s in r["strategies"]:
            assert s["max_holding_days"] == 252


# ── Pre-compute + lookup helpers ─────────────────────────────────────────────

class TestSignalPreCompute:
    def test_precompute_empty_metrics(self):
        """No metrics requested -> empty dict."""
        result = _precompute_signals("PETR4", "2023-01-01", "2023-12-31", [])
        assert result == {}

    def test_lookup_empty_signal_data(self):
        """Empty signal_data -> None."""
        assert _lookup_signal({}, "pe", "2023-01-15") is None

    def test_lookup_exact_date(self):
        """Exact date match returns value."""
        signal_data = {"pe": {"2023-01-15": 4.5}}
        assert _lookup_signal(signal_data, "pe", "2023-01-15") == 4.5

    def test_lookup_step_function(self):
        """Most recent date <= target returns value (step function)."""
        signal_data = {"pe": {"2023-01-10": 4.0, "2023-01-20": 5.0}}
        # Date between two entries -> returns the earlier one
        assert _lookup_signal(signal_data, "pe", "2023-01-15") == 4.0
        # Date after last entry -> returns the last one
        assert _lookup_signal(signal_data, "pe", "2023-01-25") == 5.0
        # Date before first entry -> None
        assert _lookup_signal(signal_data, "pe", "2023-01-05") is None


# ── Run mode (mocked) ────────────────────────────────────────────────────────

MOCK_PRICES = [
    {"date": f"2023-01-{day:02d}", "close": 30.0 + day * 0.5}
    for day in range(1, 29)
] + [
    {"date": f"2023-02-{day:02d}", "close": 44.0 - day * 0.3}
    for day in range(1, 29)
]

# Mock signal data: P/L = 4.0 for all dates (below 5.0 threshold)
MOCK_SIGNAL_DATA = {"pe": {f"2023-{m:02d}-{d:02d}": 4.0
                           for m in range(1, 3)
                           for d in range(1, 29)}}


class TestRunMode:
    def test_no_price_data(self, monkeypatch):
        """No price data -> not_found."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: [],
        )
        r = run(ticker="PETR4", strategy="value_pe",
                start_date="2023-01-01", end_date="2023-12-31")
        assert r["status"] == "not_found"

    def test_basic_backtest_shape(self, monkeypatch):
        """Backtest with mocked price data + always-true signal."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: MOCK_PRICES,
        )
        # Mock pre-compute to return signal data where P/L = 4.0 (below 5.0)
        monkeypatch.setattr(
            "skills.cvm.backtest.backtest._precompute_signals",
            lambda t, sd, ed, mn: MOCK_SIGNAL_DATA if "pe" in mn else {},
        )

        r = run(ticker="PETR4", strategy="value_pe",
                start_date="2023-01-01", end_date="2023-02-28",
                initial_capital=10000)

        assert r["status"] == "ok"
        assert r["ticker"] == "PETR4"
        assert r["strategy"] == "value_pe"
        assert "performance" in r
        assert "trades" in r
        assert "equity_curve" in r
        assert len(r["equity_curve"]) == len(MOCK_PRICES)

    def test_performance_metrics(self, monkeypatch):
        """Verify performance metrics are computed."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: MOCK_PRICES,
        )
        monkeypatch.setattr(
            "skills.cvm.backtest.backtest._precompute_signals",
            lambda t, sd, ed, mn: MOCK_SIGNAL_DATA if "pe" in mn else {},
        )

        r = run(ticker="PETR4", strategy="value_pe",
                start_date="2023-01-01", end_date="2023-02-28",
                initial_capital=10000)

        perf = r["performance"]
        assert "total_return_pct" in perf
        assert "cagr_pct" in perf
        assert "max_drawdown_pct" in perf
        assert "sharpe_ratio" in perf
        assert "win_rate_pct" in perf
        assert "num_trades" in perf
        assert "buy_hold_return_pct" in perf
        assert "alpha_vs_buy_hold" in perf

    def test_no_signal_no_trades(self, monkeypatch):
        """Signal never triggers -> no trades, capital unchanged."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: MOCK_PRICES,
        )
        # Mock pre-compute to return EMPTY signal data (no P/L values)
        monkeypatch.setattr(
            "skills.cvm.backtest.backtest._precompute_signals",
            lambda t, sd, ed, mn: {"pe": {}},
        )

        r = run(ticker="PETR4", strategy="value_pe",
                start_date="2023-01-01", end_date="2023-02-28",
                initial_capital=10000)

        assert r["status"] == "ok"
        assert r["performance"]["num_trades"] == 0
        assert r["final_equity"] == 10000.0

    def test_buy_hold_comparison(self, monkeypatch):
        """Buy & hold return is computed from first to last price."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: MOCK_PRICES,
        )
        monkeypatch.setattr(
            "skills.cvm.backtest.backtest._precompute_signals",
            lambda t, sd, ed, mn: {"pe": {}},
        )

        r = run(ticker="PETR4", strategy="value_pe",
                start_date="2023-01-01", end_date="2023-02-28")

        first_price = MOCK_PRICES[0]["close"]
        last_price = MOCK_PRICES[-1]["close"]
        expected_bh = (last_price / first_price - 1) * 100
        assert r["performance"]["buy_hold_return_pct"] == pytest.approx(expected_bh, rel=1e-2)

    def test_composite_strategy(self, monkeypatch):
        """Composite strategy needs 2 metrics (pe + roe)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: MOCK_PRICES,
        )
        # Mock pre-compute with both pe and roe
        composite_signal_data = {
            "pe": {d: 6.0 for d in MOCK_SIGNAL_DATA["pe"]},  # P/L = 6 (< 8)
            "roe": {d: 0.20 for d in MOCK_SIGNAL_DATA["pe"]},  # ROE = 20% (> 15%)
        }
        monkeypatch.setattr(
            "skills.cvm.backtest.backtest._precompute_signals",
            lambda t, sd, ed, mn: composite_signal_data,
        )

        r = run(ticker="PETR4", strategy="composite",
                start_date="2023-01-01", end_date="2023-02-28",
                initial_capital=10000)

        assert r["status"] == "ok"
        assert r["strategy"] == "composite"
        # With P/L=6 (<8) and ROE=20% (>15%), signal should trigger
        assert r["performance"]["num_trades"] > 0
