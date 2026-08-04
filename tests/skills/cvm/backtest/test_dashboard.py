"""Tests for backtest dashboard mode (v1.4 — sidebar groups + split tables + config card)."""
from __future__ import annotations
import pytest
from skills.cvm.backtest.modes.dashboard import dashboard

MOCK_PRICES = [
    {"date": f"2023-01-{day:02d}", "close": 30.0 + day * 0.5}
    for day in range(1, 29)
] + [
    {"date": f"2023-02-{day:02d}", "close": 44.0 - day * 0.3}
    for day in range(1, 29)
]
MOCK_SIGNAL_DATA = {"pe": {f"2023-{m:02d}-{d:02d}": 4.0 for m in range(1, 3) for d in range(1, 29)}}

def _patch_run_environment(monkeypatch):
    monkeypatch.setattr("skills.cvm.calculations.engines.price.price_series", lambda t, df, dt: MOCK_PRICES)
    monkeypatch.setattr("skills.cvm.backtest.modes.run._precompute_signals", lambda t, sd, ed, mn: MOCK_SIGNAL_DATA if "pe" in mn else {})

class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        r = dashboard()
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]

    def test_dashboard_tab_structure(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28", initial_capital=10000)
        assert r["status"] == "ok"
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Trades", "Performance"]
        groups = [t.get("group") for t in r["tabs"]]
        assert groups == ["Resumo", "Operações", "Desempenho"]
        for tab in r["tabs"]:
            assert "sections" in tab and isinstance(tab["sections"], list) and len(tab["sections"]) >= 1

    def test_dashboard_overview_kpis(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28")
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["CAGR", "Total Return", "Max Drawdown", "Sharpe", "Win Rate", "Alpha"]
        for kpi in r["kpis"]:
            assert "label" in kpi and "value" in kpi and "unit" in kpi

    def test_dashboard_overview_has_config_and_equity(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28")
        overview = next(t for t in r["tabs"] if t["name"] == "Overview")
        # v1.4: config table + strategy text + equity chart (+ price chart)
        assert len(overview["sections"]) >= 3
        types = [s.get("type") for s in overview["sections"]]
        assert "table" in types and "text" in types and "chart" in types

    def test_dashboard_trades_tab_has_trade_log(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28", initial_capital=10000)
        trades_tab = next(t for t in r["tabs"] if t["name"] == "Trades")
        assert len(trades_tab["sections"]) == 1
        sec = trades_tab["sections"][0]
        assert sec["title"] == "Trade Log" and sec["type"] == "table"
        for col in ("Entry Date", "Entry Price", "Exit Date", "Exit Price", "Shares", "PnL (R$)", "Return %", "Holding Days", "Exit Reason"):
            assert col in sec["columns"]
        assert len(sec["rows"]) >= 1

    def test_dashboard_performance_has_split_tables(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28")
        perf_tab = next(t for t in r["tabs"] if t["name"] == "Performance")
        assert len(perf_tab["sections"]) >= 3
        titles = [s.get("title", "") for s in perf_tab["sections"]]
        assert "Retornos" in titles and "Risco" in titles and "Qualidade" in titles

    def test_dashboard_performance_has_drawdown_chart(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28")
        perf_tab = next(t for t in r["tabs"] if t["name"] == "Performance")
        types = [s.get("type") for s in perf_tab["sections"]]
        assert "chart" in types

    def test_dashboard_propagates_run_failure(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.engines.price.price_series", lambda t, df, dt: [])
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28")
        assert r["status"] == "not_found" and "tabs" not in r

    def test_dashboard_top_level_fields(self, monkeypatch):
        _patch_run_environment(monkeypatch)
        r = dashboard(ticker="PETR4", strategy="value_pe", start_date="2023-01-01", end_date="2023-02-28")
        assert r["status"] == "ok" and r["ticker"] == "PETR4" and r["strategy"] == "value_pe"
        assert isinstance(r["tabs"], list) and isinstance(r["kpis"], list)

    def test_dashboard_unknown_strategy_propagates(self):
        r = dashboard(ticker="PETR4", strategy="nonexistent_strategy", start_date="2023-01-01", end_date="2023-02-28")
        assert r["status"] == "error"
