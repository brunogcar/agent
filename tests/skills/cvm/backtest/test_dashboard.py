"""Tests for backtest dashboard mode.

[v4] Simplified — only the error-path test remains.
"""
from __future__ import annotations
from skills.cvm.backtest.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker → error."""
        r = dashboard()
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]
