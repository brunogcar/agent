"""Tests for backtest skill route dispatch + validation."""
from __future__ import annotations
import pytest
from skills.cvm.backtest import route, MANIFEST


class TestValidation:
    def test_run_requires_ticker(self):
        from skills.cvm.backtest.backtest import run
        r = run()
        assert r["status"] == "error"

    def test_run_unknown_strategy(self):
        from skills.cvm.backtest.backtest import run
        r = run(ticker="PETR4", strategy="nonexistent")
        assert r["status"] == "error"
        assert "Unknown strategy" in r["error"]

    def test_results_requires_dict(self):
        from skills.cvm.backtest.backtest import results
        r = results()
        assert r["status"] == "error"


class TestRoute:
    def test_route_no_mode_errors(self):
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]

    def test_route_strategies(self):
        r = route(mode="strategies")
        assert r["status"] == "ok"
        assert r["count"] == 6
        names = [s["name"] for s in r["strategies"]]
        assert "value_pe" in names
        assert "composite" in names

    def test_manifest_has_3_modes(self):
        assert set(MANIFEST["modes"].keys()) == {"run", "strategies", "results"}
