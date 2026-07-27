"""tests/skills/cvm/valuation/test_route.py -- Tests for the route dispatcher.

[Phase 2C] Split out of the monolithic test_valuation.py. The two error-path
route tests need no fixture (they short-circuit before touching engines).
The dispatch test uses valuation_env so the underlying ratios() call succeeds.
"""
from __future__ import annotations


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

    def test_route_dispatches_to_ratios(self, valuation_env):
        """route(mode='ratios', company='PETR4') returns status=ok."""
        from skills.cvm.valuation import route
        result = route(mode="ratios", company="PETR4")
        assert result["status"] == "ok"
