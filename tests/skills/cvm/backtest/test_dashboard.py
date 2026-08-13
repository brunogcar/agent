"""Tests for backtest dashboard mode (v1.4 — sidebar groups + split tables + config card).

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive; we call it exactly once per file.
"""
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
        for tab in r["tabs"]:
            assert "sections" in tab and isinstance(tab["sections"], list) and len(tab["sections"]) >= 1
