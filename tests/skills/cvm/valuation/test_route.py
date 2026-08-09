"""tests/skills/cvm/valuation/test_route.py -- Tests for the route dispatcher.

[v2.1] Removed slow tests (test_route_dispatches_to_dashboard,
test_route_dispatches_to_ratios). They called route() which dispatched
to dashboard()/ratios() which hit the real DB. Only kept fast error-path
tests + manifest registration test.
"""
from __future__ import annotations

import pytest


class TestValuationRoute:
    """Tests for skills.cvm.valuation.route (the __init__.py dispatcher)."""

    def test_route_no_mode(self):
        """route() with no mode returns status=error mentioning 'mode required'."""
        from skills.cvm.valuation import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        """route() with unknown mode returns status=error mentioning 'Unknown mode'."""
        from skills.cvm.valuation import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_registers_all_four_modes(self):
        """MANIFEST['modes'] has ratios + summary + dashboard + historical_valuation."""
        from skills.cvm.valuation import MANIFEST
        modes = MANIFEST["modes"]
        assert set(modes.keys()) == {"ratios", "summary", "dashboard", "historical_valuation"}
        assert modes["ratios"]["include_in_all"] is True
        assert modes["summary"]["include_in_all"] is False
        assert modes["dashboard"]["include_in_all"] is False
        assert modes["historical_valuation"]["include_in_all"] is False

    def test_route_has_required_sources(self):
        """[v2.1] route() must have REQUIRED_SOURCES for sync guard."""
        from skills.cvm.valuation import REQUIRED_SOURCES
        assert "dfp" in REQUIRED_SOURCES
        assert "itr" in REQUIRED_SOURCES
        assert "bridge" in REQUIRED_SOURCES
