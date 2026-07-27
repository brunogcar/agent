"""Tests for the `route` dispatcher of skills/cvm/financials.

Covers TestFinancialsRoute (3 tests):
  - test_route_no_mode             : no mode → "mode required" in error
  - test_route_unknown_mode        : unknown mode → "Unknown mode" in error
  - test_route_dispatches_to_annual: route(mode="annual", company=...) → status=ok

The first two tests do NOT need the `financials_env` fixture (they short-
circuit at mode validation before any DB call). The third test uses the
fixture so route() can actually dispatch to annual().
"""
from __future__ import annotations


class TestFinancialsRoute:
    """Tests for `financials.route()` dispatcher in __init__.py."""

    def test_route_no_mode(self):
        from skills.cvm.financials import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.cvm.financials import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_annual(self, financials_env):
        from skills.cvm.financials import route
        result = route(mode="annual", company="33000167000101")
        assert result["status"] == "ok"
