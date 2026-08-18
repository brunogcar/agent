"""Tests for the dashboard mode of skills/b3/options.

Simplified pattern (2 tests):
  1. test_dashboard_no_underlying — error path (empty underlying → status=error)
  2. test_dashboard_tab_structure — returns 5 tabs with correct names + groups

[v1.2] Bumped from 4 tabs → 5 tabs (+ "Volatilidade Implícita" in the Análise group).
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
        """Dashboard returns 5 tabs with correct names + groups."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 5

        names = [t["name"] for t in result["tabs"]]
        assert names == [
            "Cadeia de Opções",
            "Put/Call Ratio",
            "Volume por Strike",
            "Exercicios",
            "Volatilidade Implícita",
        ]

        groups = [t["group"] for t in result["tabs"]]
        assert groups == [
            "Opções",
            "Análise",
            "Análise",
            "Opções",
            "Análise",
        ]

        # Each tab has a non-empty sections list.
        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1
