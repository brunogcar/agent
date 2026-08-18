"""Tests for the dashboard mode of skills/b3/price.

Simplified pattern (2 tests):
  1. test_dashboard_no_ticker — error path (empty ticker → status=error)
  2. test_dashboard_tab_structure — returns 7 tabs with correct names + groups
"""
from __future__ import annotations

import pytest


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker → status=error."""
        from skills.b3.price.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "ticker is required" in result["error"]

    def test_dashboard_tab_structure(self, price_env):
        """Dashboard returns 7 tabs with correct names + groups.

        Uses the price_env fixture from conftest.py (synthetic cotahist.db
        with 10 PETR4 trading days). The dashboard fetches ~10 years of data
        but only these 10 days exist in the synthetic DB — that's enough to
        exercise every builder + engine path.
        """
        from skills.b3.price.modes.dashboard import dashboard
        result = dashboard(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"
        assert "tabs" in result
        assert len(result["tabs"]) == 8


        # Each tab has a non-empty sections list.
        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1

        # KPIs: should have 6 cards (Preço, Variação, Abertura, Máxima, Mínima, Volume).
        assert "kpis" in result
        assert len(result["kpis"]) == 6

        # The Cotação tab must include the OHLC candlestick section.
        # [v2] The candlestick is now a vanilla Chart.js chart flagged via
        # chart_data._ohlc (rendered by the template's _renderOHLCChart), not
        # a standalone ``type: "candlestick"`` section. The chartjs-chart-
        # financial plugin was removed (it forced a time scale + required a
        # date adapter, causing blank charts).
        cotacao_tab = result["tabs"][0]
        ohlc_section = None
        for s in cotacao_tab["sections"]:
            cd = s.get("chart_data") or {}
            if cd.get("_ohlc") is True:
                ohlc_section = s
                break
        assert ohlc_section is not None, (
            "OHLC candlestick section (chart_data._ohlc=True) missing from Cotação"
        )
        # The body-bar dataset carries [bodyLow, bodyHigh] pairs + the wick
        # payload is exposed via price_full_ohlc for the range selector.
        assert cd["_ohlc_data"], "candlestick _ohlc_data payload is empty"
        assert ohlc_section.get("price_full_ohlc"), (
            "candlestick price_full_ohlc missing (needed for range-filter wicks)"
        )
        body_ds = ohlc_section["chart_data"]["data"]["datasets"][0]
        assert isinstance(body_ds["data"][0], list) and len(body_ds["data"][0]) == 2, (
            "candlestick body dataset must be [[bodyLow, bodyHigh], ...] floating bars"
        )
