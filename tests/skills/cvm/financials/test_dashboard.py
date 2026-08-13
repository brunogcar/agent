"""Tests for the `dashboard` mode of skills/cvm/financials (v1.12).

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive; we call it exactly once per file.

Uses the shared `financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestDashboardMode:
    """[v1.12] Tests for `financials.dashboard()` — 7-tab composition mode."""

    def test_dashboard_no_company(self, financials_env):
        """Empty company → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, financials_env):
        """Returns 11 tabs with grouped sidebar."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 11
        expected_names = [
            "Overview", "Indicadores", "Crescimento",
            "Balanço", "DRE", "DFC", "DVA",
            "Anual", "Trimestral",
            "Anualizado", "Trimestral YoY",
        ]
        assert [t["name"] for t in result["tabs"]] == expected_names
        # Every tab must have a `sections` list.
        for tab in result["tabs"]:
            assert "sections" in tab, f"tab {tab['name']} missing 'sections'"
            assert isinstance(tab["sections"], list)
