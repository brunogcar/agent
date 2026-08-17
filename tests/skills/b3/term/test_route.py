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
