"""Tests for the `route` dispatcher of skills/cvm/financials.

Covers TestFinancialsRoute (4 tests):
  - test_route_no_mode             : no mode → "mode required" in error
  - test_route_unknown_mode        : unknown mode → "Unknown mode" in error
  - test_route_dispatches_to_annual: route(mode="annual", company=...) → status=ok
  - test_route_dispatches_to_dashboard: route(mode="dashboard", company=...) → status=ok
                                       (v1.5 — new mode)

The first two tests do NOT need the `financials_env` fixture (they short-
circuit at mode validation before any DB call). The third + fourth use the
fixture so route() can actually dispatch to annual() / dashboard().
"""
from __future__ import annotations


class TestFinancialsRoute:
    """Tests for `financials.route()` dispatcher in __init__.py."""

    def test_route_no_mode(self):
        from skills.cvm.financials import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.cvm.financials import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_annual(self, financials_env):
        from skills.cvm.financials import route
        result = route(mode="annual", company="33000167000101")
        assert result["status"] == "ok"

    def test_route_dispatches_to_dashboard(self, financials_env):
        """[v1.16] route(mode="dashboard", ...) dispatches to dashboard() and
        returns the 11-tab payload with sidebar grouping.
        [v2.3] Tab 9 renamed from "Trimestral" to "Trimestral QoQ" per user
        request. Test updated to match."""
        from skills.cvm.financials import route
        result = route(mode="dashboard", company="33000167000101")
        assert result["status"] == "ok"
        assert "tabs" in result
        tab_names = [t["name"] for t in result["tabs"]]
        assert tab_names == [
            "Overview", "Indicadores", "Crescimento",
            "Balanço", "DRE", "DFC", "DVA",
            "Anual", "Trimestral QoQ",
            "Anualizado", "Trimestral YoY",
        ]
        # KPIs are at top level, not inside tabs.
        assert "kpis" in result
        assert len(result["kpis"]) >= 6  # 6 KPI cards expected
