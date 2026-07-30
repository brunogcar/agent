"""Tests for skills/cvm/comparison/ — summary mode.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers the summary mode (single quick-compare table with ~10 KPI columns).
"""
from __future__ import annotations

from skills.cvm.comparison.modes.summary import summary
from tests.skills.cvm.comparison.conftest import (
    VAL_PETR4, VAL_VALE3, FIN_PETR4, FIN_VALE3, DIV_PETR4, DIV_VALE3,
)


class TestSummary:
    def test_basic_shape(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = summary(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert len(r["sections"]) == 1
        sec = r["sections"][0]
        assert sec["title"] == "Quick Compare"
        # ~10 KPI columns + Ticker
        assert "P/L" in sec["columns"]
        assert "ROE" in sec["columns"]
        assert "Receita Líquida" in sec["columns"]
        assert len(sec["rows"]) == 2

    def test_summary_has_kpi_values(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = summary(tickers=["PETR4", "VALE3"])
        sec = r["sections"][0]
        pl_idx = sec["columns"].index("P/L")
        # PETR4 P/L = 8.2, VALE3 P/L = 6.5
        assert sec["rows"][0][pl_idx] == 8.2
        assert sec["rows"][1][pl_idx] == 6.5
