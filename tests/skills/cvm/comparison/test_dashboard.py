"""Tests for comparison dashboard mode.

[v4] Simplified — only the error-path test remains.
"""
from __future__ import annotations
from skills.cvm.comparison.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_requires_tickers(self):
        """No tickers → validation error."""
        r = dashboard()
        assert r["status"] == "error"
        assert "tickers" in r["error"]
