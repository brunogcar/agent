"""Tests for skills/cvm/comparison/ — route dispatch.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers the route() dispatcher in skills/cvm/comparison/__init__.py:
  - no mode → error
  - unknown mode → error
  - mode="side_by_side" → dispatches to comparison.side_by_side()
"""
from __future__ import annotations

from skills.cvm.comparison import route
from tests.skills.cvm.comparison.conftest import (
    VAL_PETR4, VAL_VALE3, FIN_PETR4, FIN_VALE3, DIV_PETR4, DIV_VALE3,
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
