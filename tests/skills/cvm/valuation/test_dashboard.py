"""Tests for valuation dashboard mode.

[v4] Simplified — only the error-path test remains.
"""
from __future__ import annotations
from skills.cvm.valuation.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self, valuation_env):
        """Empty company → status=error."""
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]
