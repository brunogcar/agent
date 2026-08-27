"""Tests for historical dashboard mode.

[v4] Simplified — only the error-path test remains.
"""
from __future__ import annotations
from skills.cvm.historical.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company → error."""
        r = dashboard()
        assert r["status"] == "error"
