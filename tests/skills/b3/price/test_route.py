"""Tests for the route dispatcher of skills/b3/price.

2 tests:
  1. test_route_no_mode — route() with no mode returns status=error
  2. test_route_registers_modes — MANIFEST has dashboard + quote modes
"""
from __future__ import annotations

import pytest


class TestPriceRoute:
    def test_route_no_mode(self):
        """route() with no mode returns status=error mentioning 'mode required'."""
        from skills.b3.price import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_registers_modes(self):
        """MANIFEST['modes'] has both dashboard + quote, with correct params."""
        from skills.b3.price import MANIFEST
        modes = MANIFEST["modes"]
        assert set(modes.keys()) == {"dashboard", "quote"}
        # Both modes require a ticker param.
        assert "ticker" in modes["dashboard"]["params"]
        assert "ticker" in modes["quote"]["params"]
        # Neither is included in sub_domain="all" runs.
        assert modes["dashboard"]["include_in_all"] is False
        assert modes["quote"]["include_in_all"] is False
        # cotahist is required.
        from skills.b3.price import REQUIRED_SOURCES
        assert "cotahist" in REQUIRED_SOURCES
