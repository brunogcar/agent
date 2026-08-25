"""Tests for the route + manifest of skills/b3/term."""
from __future__ import annotations


class TestTermRoute:
    def test_route_no_mode(self):
        """No mode → status=error."""
        from skills.b3.term import route
        result = route()
        assert result["status"] == "error"

    def test_route_registers_modes(self):
        """MANIFEST has the dashboard mode registered."""
        from skills.b3.term import MANIFEST
        assert "modes" in MANIFEST
        modes = MANIFEST["modes"]
        assert "dashboard" in modes

    def test_required_sources_includes_forward_fallback(self):
        """[v2] REQUIRED_SOURCES includes b3-api-derivatives + b3-api-instruments.

        The term skill's forward-data fallback (EQUITY FORWARD snapshot for
        stock tickers without COTAHIST term data) needs both b3.api DBs.
        """
        from skills.b3.term import REQUIRED_SOURCES
        assert "cotahist" in REQUIRED_SOURCES
        assert "b3-api-derivatives" in REQUIRED_SOURCES
        assert "b3-api-instruments" in REQUIRED_SOURCES
