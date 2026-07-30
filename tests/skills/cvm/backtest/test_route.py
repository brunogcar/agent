"""Tests for backtest skill route dispatch + validation."""
from __future__ import annotations
import pytest
from skills.cvm.backtest import route, MANIFEST


class TestValidation:
    def test_run_requires_ticker(self):
        from skills.cvm.backtest.modes.run import run
        r = run()
        assert r["status"] == "error"

    def test_run_unknown_strategy(self):
        from skills.cvm.backtest.modes.run import run
        r = run(ticker="PETR4", strategy="nonexistent")
        assert r["status"] == "error"
        assert "Unknown strategy" in r["error"]

    def test_results_requires_dict(self):
        from skills.cvm.backtest.modes.results import results
        r = results()
        assert r["status"] == "error"

    def test_dashboard_requires_ticker(self):
        from skills.cvm.backtest.modes.dashboard import dashboard
        r = dashboard()
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]


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

    def test_manifest_has_4_modes(self):
        assert set(MANIFEST["modes"].keys()) == {
            "run", "strategies", "results", "dashboard"
        }

    def test_manifest_run_includes_in_all(self):
        # `run` is the default mode (include_in_all=True)
        assert MANIFEST["modes"]["run"]["include_in_all"] is True

    def test_manifest_aux_modes_not_in_all(self):
        # strategies / results / dashboard are not auto-run by sub_domain=all
        for mode in ("strategies", "results", "dashboard"):
            assert MANIFEST["modes"][mode]["include_in_all"] is False

    def test_route_dispatches_to_dashboard_no_ticker(self):
        """dashboard() with no ticker -> error (does NOT touch price engine)."""
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]
