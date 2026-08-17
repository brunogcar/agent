"""Tests for the dashboard mode of skills/b3/term.

Simplified pattern (2 tests):
  1. test_dashboard_no_ticker — error path (empty ticker → status=error)
  2. test_dashboard_tab_structure — returns 3 tabs with correct names + groups
"""
from __future__ import annotations


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker → status=error."""
        from skills.b3.term.modes.dashboard import dashboard
        result = dashboard(ticker="")
        assert result["status"] == "error"

    def test_dashboard_tab_structure(self):
        """Dashboard returns 3 tabs with correct names + groups.

        Uses graceful degradation — if no DB, tabs get error sections.
        """
        from skills.b3.term.modes.dashboard import dashboard
        result = dashboard(ticker="PETR4")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 3

        names = [t["name"] for t in result["tabs"]]
        assert names == [
            "Contratos Ativos",
            "Spread Termo vs Spot",
            "Volume Histórico",
        ]

        groups = [t["group"] for t in result["tabs"]]
        assert groups == [
            "Termo",
            "Análise",
            "Análise",
        ]

        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1
