"""Tests for skills/cvm/comparison/ — side_by_side mode.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers the side_by_side mode end-to-end: section shape, column labels,
row alignment, per-column format specs, best-effort behavior when one
ticker fails, ticker uppercasing, and dividend metric extraction (the
_extract_dividend_metrics helper is internal to side_by_side's data
assembly).

The synthetic skill results (VAL_*, FIN_*, DIV_*) live in conftest.py
and include the [v1.3] additions to valuation.ratios (roe, roa,
margem_liquida, divida_pl, liquidez_corrente).
"""
from __future__ import annotations

import pytest

from skills.cvm.comparison import comparison
from tests.skills.cvm.comparison.conftest import (
    VAL_PETR4, VAL_VALE3, FIN_PETR4, FIN_VALE3, DIV_PETR4, DIV_VALE3,
)


class TestSideBySide:
    def test_basic_shape(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert set(r["sections"].keys()) == {"valuation", "financials", "dividends"}
        assert r["errors"] == []

    def test_valuation_section_shape(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        val = r["sections"]["valuation"]
        assert val["columns"][0] == "Ticker"
        assert "P/L" in val["columns"]
        assert "Market Cap" in val["columns"]
        # 2 tickers -> 2 rows
        assert len(val["rows"]) == 2
        assert val["rows"][0][0] == "PETR4"
        assert val["rows"][1][0] == "VALE3"
        # P/L value landed (PETR4 = 8.2)
        pl_idx = val["columns"].index("P/L")
        assert val["rows"][0][pl_idx] == 8.2
        assert val["rows"][1][pl_idx] == 6.5

    def test_valuation_section_has_v13_calculations_metrics(self, mock_skills, monkeypatch):
        """[v1.3] New calculations-sourced metrics render in valuation section."""
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        val = r["sections"]["valuation"]
        # New columns present
        assert "ROE (val)" in val["columns"]
        assert "ROA (val)" in val["columns"]
        assert "Marg. Líq. (val)" in val["columns"]
        assert "Dívida/PL" in val["columns"]
        assert "Liquidez Corrente" in val["columns"]
        # PETR4 ROE from val_ratios = 0.25
        roe_idx = val["columns"].index("ROE (val)")
        assert val["rows"][0][roe_idx] == 0.25
        assert val["rows"][1][roe_idx] == 0.18
        # PETR4 Liquidez Corrente = 1.8
        liq_idx = val["columns"].index("Liquidez Corrente")
        assert val["rows"][0][liq_idx] == 1.8
        # PETR4 Dívida/PL = 0.50
        dpl_idx = val["columns"].index("Dívida/PL")
        assert val["rows"][0][dpl_idx] == 0.50
        # Format specs
        assert val["formats"]["ROE (val)"] == "pct"
        assert val["formats"]["Dívida/PL"] == "num"
        assert val["formats"]["Liquidez Corrente"] == "num"

    def test_financials_section_shape(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        fin = r["sections"]["financials"]
        assert "Receita Líquida" in fin["columns"]
        assert "ROE" in fin["columns"]
        rec_idx = fin["columns"].index("Receita Líquida")
        assert fin["rows"][0][rec_idx] == 400_000_000_000

    def test_dividends_section_shape(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        div = r["sections"]["dividends"]
        assert "Eventos (B3)" in div["columns"]
        assert "Dividendos (últ ano)" in div["columns"]
        ev_idx = div["columns"].index("Eventos (B3)")
        assert div["rows"][0][ev_idx] == 3  # PETR4 had 3 events

    def test_formats_per_column(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        val = r["sections"]["valuation"]
        assert val["formats"]["Ticker"] == "text"
        assert val["formats"]["P/L"] == "num"
        assert val["formats"]["Market Cap"] == "brl"
        assert val["formats"]["Div Yield"] == "pct"

    def test_best_effort_one_ticker_fails(self, mock_skills, monkeypatch):
        """If valuation fails for one ticker, comparison still returns the others."""
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": {"status": "error", "error": "no price"}},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        # VALE3's valuation cells are None (price lookup failed)
        val = r["sections"]["valuation"]
        price_idx = val["columns"].index("Preço")
        assert val["rows"][0][price_idx] == 38.5      # PETR4 OK
        assert val["rows"][1][price_idx] is None       # VALE3 failed
        # errors list captured VALE3's valuation failure
        assert any("valuation" in e for e in r["errors"])
        assert len(r["errors"]) == 1

    def test_uppercases_tickers(self, mock_skills, monkeypatch):
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = comparison.side_by_side(tickers=["petr4", "vale3"])
        assert r["tickers"] == ["PETR4", "VALE3"]


# ── Internal helper: dividend metric extraction ──────────────────────────────
# Tested here because _extract_dividend_metrics is called from _fetch_all,
# which is called from side_by_side. Pure-Python — no monkeypatch needed.

class TestExtractDividendMetrics:
    def test_extracts_event_count_and_dpa_avg(self):
        sections = {"recent_events": {"status": "ok", "count": 3,
                                      "events": [{"rate": 1.5}, {"rate": 2.0}, {"rate": 1.0}]}}
        m = comparison._extract_dividend_metrics(sections)
        assert m["event_count"] == 3
        assert m["b3_dpa_avg"] == pytest.approx(1.5)  # (1.5+2.0+1.0)/3

    def test_extracts_annual_totals(self):
        sections = {"annual_trend": {"status": "ok", "periods": [
            {"accounts": {"7.08.04": {"valor_brl": 30_000_000_000},
                          "7.08.04.01": {"valor_brl": 5_000_000_000},
                          "7.08.04.02": {"valor_brl": 25_000_000_000}}}]}}
        m = comparison._extract_dividend_metrics(sections)
        assert m["annual_total"] == 30_000_000_000
        assert m["annual_jcp"] == 5_000_000_000
        assert m["annual_dividendos"] == 25_000_000_000

    def test_empty_sections_return_nones(self):
        m = comparison._extract_dividend_metrics({})
        assert m["event_count"] is None
        assert m["annual_total"] is None
