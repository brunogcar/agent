"""Tests for the dashboard mode of skills/b3/options.

Simplified pattern (2 tests):
  1. test_dashboard_no_underlying — error path (empty underlying → status=error)
  2. test_dashboard_tab_structure — returns 3 tabs with correct names + groups
"""
from __future__ import annotations


class TestDashboardMode:
    def test_dashboard_no_underlying(self):
        """Empty underlying → status=error."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="")
        assert result["status"] == "error"
        assert "underlying" in result["error"].lower()

    def test_dashboard_tab_structure(self, options_env):
        """Dashboard returns 4 tabs with correct names + groups."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 4

        names = [t["name"] for t in result["tabs"]]
        assert names == [
            "Cadeia de Opções",
            "Put/Call Ratio",
            "Volume por Strike",
            "Exercicios",
        ]

        groups = [t["group"] for t in result["tabs"]]
        assert groups == [
            "Opções",
            "Análise",
            "Análise",
            "Opções",
        ]

        # Each tab has a non-empty sections list.
        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1
