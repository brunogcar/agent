"""Tests for financials dashboard mode.

[v4] Simplified — only the error-path test remains.
"""
from __future__ import annotations
from skills.cvm.financials.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self, financials_env):
        """Empty company → status=error (does NOT touch DBs)."""
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]
