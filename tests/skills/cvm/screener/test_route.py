"""Tests for skills/cvm/screener/ — route dispatch.

[Phase 4] Split out of the original single-file `test_screener.py`.
Covers the route() dispatcher in skills/cvm/screener/__init__.py:
  - no mode → error
  - unknown mode → error
"""
from __future__ import annotations

from skills.cvm.screener import route


class TestRoute:
    def test_route_no_mode_errors(self):
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]
