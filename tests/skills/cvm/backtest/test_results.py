"""Tests for backtest results mode."""
from __future__ import annotations

import pytest
from skills.cvm.backtest.backtest import results


class TestResultsMode:
    def test_requires_dict(self):
        r = results()
        assert r["status"] == "error"

    def test_passes_through_error(self):
        r = results({"status": "error", "error": "something went wrong"})
        assert r["status"] == "error"

    def test_extracts_summary(self):
        backtest = {
            "status": "ok",
            "ticker": "PETR4",
            "strategy": "value_pe",
            "performance": {
                "total_return_pct": 25.5,
                "cagr_pct": 8.0,
                "max_drawdown_pct": 12.3,
                "sharpe_ratio": 1.2,
                "win_rate_pct": 60.0,
                "alpha_vs_buy_hold": 5.0,
            },
            "trades": [
                {"entry_date": "2023-01-15", "exit_date": "2023-03-15",
                 "return_pct": 10.0, "holding_days": 60, "pnl": 1000, "shares": 100,
                 "entry_price": 30.0, "exit_price": 33.0, "exit_reason": "max_holding"},
                {"entry_date": "2023-04-01", "exit_date": "2023-06-01",
                 "return_pct": -5.0, "holding_days": 61, "pnl": -500, "shares": 100,
                 "entry_price": 33.0, "exit_price": 31.35, "exit_reason": "max_holding"},
            ],
        }
        r = results(backtest)
        assert r["status"] == "ok"
        assert r["summary"]["total_return_pct"] == 25.5
        assert r["summary"]["cagr_pct"] == 8.0
        assert r["trade_analysis"]["num_trades"] == 2
        assert r["trade_analysis"]["avg_holding_days"] == 60.5
        assert r["trade_analysis"]["best_trade"]["return_pct"] == 10.0
        assert r["trade_analysis"]["worst_trade"]["return_pct"] == -5.0

    def test_no_trades(self):
        backtest = {
            "status": "ok",
            "ticker": "PETR4",
            "strategy": "value_pe",
            "performance": {"total_return_pct": 0, "cagr_pct": 0,
                            "max_drawdown_pct": 0, "sharpe_ratio": 0,
                            "win_rate_pct": 0, "alpha_vs_buy_hold": 0},
            "trades": [],
        }
        r = results(backtest)
        assert r["status"] == "ok"
        assert r["trade_analysis"]["num_trades"] == 0
        assert r["trade_analysis"]["best_trade"] is None
        assert r["trade_analysis"]["worst_trade"] is None
