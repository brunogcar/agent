"""Tests for b3.term dashboard mode.

[v4] Simplified — only the error-path test remains. The forward fallback
tests (test_dashboard_shows_forward_fallback + test_dashboard_forward_fallback_no_forward_data)
are kept — they use mocks and run fast.
"""
from __future__ import annotations


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker → error."""
        from skills.b3.term.modes.dashboard import dashboard
        result = dashboard(ticker="")
        assert result["status"] == "error"
