"""Tests for b3.options dashboard mode.

[v4] Simplified — only the error-path test remains.
[v5] Fix: dashboard() defaults to underlying="PETR", so calling it with
no args runs the FULL 6-tab dashboard against real DBs (7s+). Pass
underlying="" to actually test the error path (instant return).
"""
from __future__ import annotations
from skills.b3.options.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_underlying(self):
        """Empty underlying → error (instant return, no DB access)."""
        r = dashboard(underlying="")
        assert r["status"] == "error"
        assert "underlying" in r["error"].lower()
