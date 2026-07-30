"""Tests for backtest dashboard mode (skills.cvm.backtest.modes.dashboard).

Mirrors the pattern from tests/skills/cvm/valuation/test_dashboard.py — the
dashboard mode is a thin composition of run() that reshapes the run() result
into a 3-tab payload (Overview / Trades / Performance). These tests cover:
  - Empty ticker -> error (does NOT touch price engine).
  - Tab structure (3 tabs with exact names + sections lists).
  - KPI cards (6: CAGR, Total Return, Max Drawdown, Sharpe, Win Rate, Alpha).
  - Overview tab: Strategy text section + Equity Curve chart section.
  - Trades tab: trade log table (entry/exit dates+prices, shares, PnL, etc.).
  - Performance tab: performance summary table (8 metrics).
  - Propagation: when run() returns not_found (no price data), dashboard
    returns the same not_found dict instead of rendering empty tabs.
"""
from __future__ import annotations

import pytest

from skills.cvm.backtest.modes.dashboard import dashboard


# ── Synthetic price series + signal data ─────────────────────────────────────
# Same fixtures as tests/skills/cvm/backtest/test_run.py — kept inline so the
# dashboard tests don't depend on test_run.py's module-level constants.

MOCK_PRICES = [
    {"date": f"2023-01-{day:02d}", "close": 30.0 + day * 0.5}
    for day in range(1, 29)
] + [
    {"date": f"2023-02-{day:02d}", "close": 44.0 - day * 0.3}
    for day in range(1, 29)
]

MOCK_SIGNAL_DATA = {"pe": {f"2023-{m:02d}-{d:02d}": 4.0
                           for m in range(1, 3)
                           for d in range(1, 29)}}


def _patch_run_environment(monkeypatch):
    """Patch the price engine + signal precompute used by run()."""
    monkeypatch.setattr(
        "skills.cvm.calculations.engines.price.price_series",
        lambda t, df, dt: MOCK_PRICES,
    )
    monkeypatch.setattr(
        "skills.cvm.backtest.modes.run._precompute_signals",
        lambda t, sd, ed, mn: MOCK_SIGNAL_DATA if "pe" in mn else {},
    )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker -> status=error with 'ticker is required'."""
        r = dashboard()
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]

    def test_dashboard_tab_structure(self, monkeypatch):
        """3 tabs with exact names: Overview, Trades, Performance."""
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28",
                      initial_capital=10000)
        assert r["status"] == "ok"
        assert "tabs" in r
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Trades", "Performance"]
        # Each tab has a non-empty sections list
        for tab in r["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1

    def test_dashboard_overview_kpis(self, monkeypatch):
        """6 KPI cards with exact labels + unit field for adapter formatting."""
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28")
        assert "kpis" in r
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["CAGR", "Total Return", "Max Drawdown",
                          "Sharpe", "Win Rate", "Alpha"]
        # Each KPI card has label + value + unit (used by adapter to format).
        for kpi in r["kpis"]:
            assert "label" in kpi
            assert "value" in kpi
            assert "unit" in kpi

    def test_dashboard_overview_tab_has_strategy_and_equity(self, monkeypatch):
        """Overview tab has Strategy text section + Equity Curve chart section."""
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28")
        overview = next(t for t in r["tabs"] if t["name"] == "Overview")
        assert len(overview["sections"]) == 2
        strategy_sec, equity_sec = overview["sections"]
        # Strategy section is text with ticker + strategy name in body.
        assert strategy_sec["type"] == "text"
        assert strategy_sec["title"] == "Strategy"
        assert "PETR4" in strategy_sec["text"]
        assert "value_pe" in strategy_sec["text"]
        # Equity curve section is a chart with full Chart.js config.
        assert equity_sec["type"] == "chart"
        assert equity_sec["title"] == "Equity Curve"
        cfg = equity_sec["chart_data"]
        assert cfg["type"] == "line"
        assert "datasets" in cfg["data"]
        assert cfg["data"]["datasets"][0]["label"] == "Equity (R$)"
        # Equity curve values land oldest-first, same length as price series.
        assert len(cfg["data"]["datasets"][0]["data"]) == len(MOCK_PRICES)

    def test_dashboard_trades_tab_has_trade_log(self, monkeypatch):
        """Trades tab has a Trade Log table with the right columns."""
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28",
                      initial_capital=10000)
        trades_tab = next(t for t in r["tabs"] if t["name"] == "Trades")
        assert len(trades_tab["sections"]) == 1
        sec = trades_tab["sections"][0]
        assert sec["title"] == "Trade Log"
        assert sec["type"] == "table"
        # Columns match the trade dict emitted by run() exactly.
        for col in ("Entry Date", "Entry Price", "Exit Date", "Exit Price",
                    "Shares", "PnL (R$)", "Return %", "Holding Days",
                    "Exit Reason"):
            assert col in sec["columns"]
        # With P/L < 5 signal triggering on every bar, we should have trades.
        assert len(sec["rows"]) >= 1
        # Format specs for each column.
        assert sec["formats"]["Entry Price"] == "brl_full"
        assert sec["formats"]["Return %"] == "pct_raw"
        assert sec["formats"]["Shares"] == "int"

    def test_dashboard_performance_tab_has_summary(self, monkeypatch):
        """Performance tab has a Performance Summary table with all metrics."""
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28")
        perf_tab = next(t for t in r["tabs"] if t["name"] == "Performance")
        assert len(perf_tab["sections"]) == 1
        sec = perf_tab["sections"][0]
        assert sec["title"] == "Performance Summary"
        assert sec["type"] == "table"
        assert sec["columns"] == ["Metric", "Value"]
        # All 8 performance metrics are present (one row each).
        rows_text = " ".join(str(row[0]) for row in sec["rows"])
        for metric in ("Total Return", "CAGR", "Max Drawdown", "Sharpe Ratio",
                       "Win Rate", "Number of Trades", "Buy & Hold Return",
                       "Alpha vs Buy & Hold"):
            assert metric in rows_text, f"Missing metric: {metric}"

    def test_dashboard_propagates_run_failure(self, monkeypatch):
        """When run() returns not_found (no price data), dashboard returns the
        same not_found dict instead of rendering empty tabs."""
        monkeypatch.setattr(
            "skills.cvm.calculations.engines.price.price_series",
            lambda t, df, dt: [],
        )
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28")
        assert r["status"] == "not_found"
        assert "tabs" not in r

    def test_dashboard_top_level_fields(self, monkeypatch):
        """Top-level dashboard fields: status, ticker, strategy, tabs, kpis."""
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe",
                      start_date="2023-01-01", end_date="2023-02-28")
        assert r["status"] == "ok"
        assert r["ticker"] == "PETR4"
        assert r["strategy"] == "value_pe"
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_unknown_strategy_propagates(self):
        """Unknown strategy -> dashboard returns run()'s error dict."""
        r = dashboard(ticker="PETR4", strategy="nonexistent")
        assert r["status"] == "error"
        assert "Unknown strategy" in r["error"]
        assert "tabs" not in r
