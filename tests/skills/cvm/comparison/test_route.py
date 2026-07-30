"""Tests for skills/cvm/comparison/ — route dispatch.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers the route() dispatcher in skills/cvm/comparison/__init__.py:
  - no mode → error
  - unknown mode → error
  - mode="side_by_side" → dispatches to comparison.side_by_side()
  - mode="dashboard" → dispatches to comparison.dashboard()
  - manifest lists all 4 modes + include_in_all flags are correct
"""
from __future__ import annotations

from skills.cvm.comparison import route, MANIFEST
from skills.cvm.comparison._registry import MODES
from tests.skills.cvm.comparison.conftest import (
    VAL_PETR4, VAL_VALE3, FIN_PETR4, FIN_VALE3, DIV_PETR4, DIV_VALE3,
    FIN_QUARTERLY_SUZB3,
)


class TestRoute:
    def test_route_no_mode_errors(self):
        r = route()
        assert r["status"] == "error"
        assert "mode" in r["error"]

    def test_route_unknown_mode_errors(self):
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]

    def test_route_side_by_side(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = route(mode="side_by_side", tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"

    def test_route_dashboard_dispatches(self, mock_skills, monkeypatch):
        """route(mode='dashboard') dispatches to the new dashboard mode."""
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        # Mock the financials.quarterly call made by the growth mode that
        # dashboard() calls internally.
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)

        r = route(mode="dashboard", tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert "tabs" in r
        assert "kpis" in r

    def test_route_dashboard_validation_error(self):
        """route(mode='dashboard') with no tickers returns the side_by_side
        validation error verbatim."""
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "tickers" in r["error"]


class TestManifest:
    def test_manifest_has_4_modes(self):
        assert set(MANIFEST["modes"].keys()) == {
            "side_by_side", "summary", "growth", "dashboard",
        }

    def test_registry_has_4_modes(self):
        assert set(MODES.keys()) == {
            "side_by_side", "summary", "growth", "dashboard",
        }

    def test_summary_includes_in_all(self):
        """summary mode is the only one with include_in_all=True."""
        assert MANIFEST["modes"]["summary"]["include_in_all"] is True

    def test_other_modes_not_in_all(self):
        """side_by_side / growth / dashboard are not in all."""
        for mode in ("side_by_side", "growth", "dashboard"):
            assert MANIFEST["modes"][mode]["include_in_all"] is False
