"""Tests for skills/cvm/comparison/ — multi-ticker comparison skill.

Covers: input validation, side_by_side shape, summary shape, best-effort
per-ticker (one ticker failing doesn't break the whole comparison), and
dividend metric extraction. Uses monkeypatch to mock the underlying skills
so no database/network is needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.comparison.modes.side_by_side import side_by_side
from skills.cvm.comparison.modes.summary import summary
from skills.cvm.comparison.modes.growth import growth
from skills.cvm.comparison.fetchers import _extract_dividend_metrics
from skills.cvm.comparison.helpers import _pct_change


# ── Synthetic skill results (mirror the real skill output shapes) ────────────

VAL_PETR4 = {
    "status": "ok", "ticker": "PETR4",
    "ratios": {"price": 38.5, "p_l": 8.2, "p_vpa": 1.9, "ev_ebitda": 4.5,
               "dividend_yield": 0.12, "market_cap": 500_000_000_000,
               "total_shares": 13_000_000_000, "eps": 4.7, "vpa": 20.1,
               "ev": 510_000_000_000, "psr": 1.2, "p_ebit": 6.1, "dpa": 2.5},
    "sources": {},
}
VAL_VALE3 = {
    "status": "ok", "ticker": "VALE3",
    "ratios": {"price": 60.0, "p_l": 6.5, "p_vpa": 1.5, "ev_ebitda": 3.8,
               "dividend_yield": 0.09, "market_cap": 300_000_000_000,
               "total_shares": 5_000_000_000, "eps": 9.2, "vpa": 40.0,
               "ev": 320_000_000_000, "psr": 2.1, "p_ebit": 5.0, "dpa": 3.1},
    "sources": {},
}

FIN_PETR4 = {
    "status": "ok", "company": "PETROBRAS", "sections": {
        "latest_annual": {"period": "2024", "status": "ok",
                          "metrics": {"receita_liquida": 400_000_000_000,
                                      "lucro_bruto": 120_000_000_000,
                                      "ebit": 80_000_000_000,
                                      "ebitda": 100_000_000_000,
                                      "lucro_liquido": 60_000_000_000,
                                      "ativo_total": 1_000_000_000_000,
                                      "patrimonio_liquido": 400_000_000_000,
                                      "caixa": 50_000_000_000,
                                      "divida_bruta": 200_000_000_000,
                                      "fco": 90_000_000_000},
                          "ratios": {"marg_bruta": 0.30, "marg_ebitda": 0.25,
                                     "marg_liquida": 0.15, "roe": 0.15,
                                     "roa": 0.06, "payout": 0.50}},
        "quarterly_trend": [], "latest_quarterly": {},
    },
}
FIN_VALE3 = {
    "status": "ok", "company": "VALE", "sections": {
        "latest_annual": {"period": "2024", "status": "ok",
                          "metrics": {"receita_liquida": 300_000_000_000,
                                      "lucro_bruto": 100_000_000_000,
                                      "ebit": 70_000_000_000,
                                      "ebitda": 85_000_000_000,
                                      "lucro_liquido": 50_000_000_000,
                                      "ativo_total": 800_000_000_000,
                                      "patrimonio_liquido": 350_000_000_000,
                                      "caixa": 40_000_000_000,
                                      "divida_bruta": 150_000_000_000,
                                      "fco": 80_000_000_000},
                          "ratios": {"marg_bruta": 0.33, "marg_ebitda": 0.28,
                                     "marg_liquida": 0.17, "roe": 0.14,
                                     "roa": 0.06, "payout": 0.60}},
        "quarterly_trend": [], "latest_quarterly": {},
    },
}

DIV_PETR4 = {
    "status": "ok", "company": "PETR4", "sections": {
        "recent_events": {"status": "ok", "count": 3,
                          "events": [{"rate": 1.5}, {"rate": 2.0}, {"rate": 1.0}]},
        "annual_trend": {"status": "ok", "periods": [{"data_fim_exerc": "2024-12-31",
                          "accounts": {"7.08.04": {"valor_brl": 30_000_000_000},
                                       "7.08.04.01": {"valor_brl": 5_000_000_000},
                                       "7.08.04.02": {"valor_brl": 25_000_000_000}}}]},
        "payable": {},
    },
}
DIV_VALE3 = {
    "status": "ok", "company": "VALE3", "sections": {
        "recent_events": {"status": "ok", "count": 2,
                          "events": [{"rate": 2.5}, {"rate": 3.0}]},
        "annual_trend": {"status": "ok", "periods": [{"data_fim_exerc": "2024-12-31",
                          "accounts": {"7.08.04": {"valor_brl": 20_000_000_000},
                                       "7.08.04.01": {"valor_brl": 2_000_000_000},
                                       "7.08.04.02": {"valor_brl": 18_000_000_000}}}]},
        "payable": {},
    },
}


def _mock_skills(monkeypatch, val_map, fin_map, div_map):
    """Monkeypatch the 3 underlying skills to return synthetic data."""
    def fake_val_ratios(company=""):
        return val_map.get(company.strip().upper(),
                           {"status": "error", "error": f"no data for {company}"})
    def fake_fin_summary(company="", consolidado=1):
        return fin_map.get(company.strip().upper(),
                           {"status": "error", "error": f"no data for {company}"})
    def fake_div_summary(company=""):
        return div_map.get(company.strip().upper(),
                           {"status": "error", "error": f"no data for {company}"})
    monkeypatch.setattr("skills.cvm.valuation.modes.ratios.ratios", fake_val_ratios)
    monkeypatch.setattr("skills.cvm.financials.modes.summary.summary", fake_fin_summary)
    monkeypatch.setattr("skills.cvm.dividends.dividends.summary", fake_div_summary)


# ── Input validation ─────────────────────────────────────────────────────────

class TestValidation:
    def test_side_by_side_requires_tickers(self):
        r = side_by_side()
        assert r["status"] == "error"
        assert "tickers" in r["error"]

    def test_side_by_side_requires_list(self):
        r = side_by_side(tickers="PETR4")
        assert r["status"] == "error"

    def test_side_by_side_requires_min_two(self):
        r = side_by_side(tickers=["PETR4"])
        assert r["status"] == "error"
        assert "2 tickers" in r["error"]

    def test_summary_requires_tickers(self):
        r = summary()
        assert r["status"] == "error"

    def test_summary_requires_min_two(self):
        r = summary(tickers=["PETR4"])
        assert r["status"] == "error"


# ── side_by_side mode ────────────────────────────────────────────────────────

class TestSideBySide:
    def test_basic_shape(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert set(r["sections"].keys()) == {"valuation", "financials", "dividends"}
        assert r["errors"] == []

    def test_valuation_section_shape(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["PETR4", "VALE3"])
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

    def test_financials_section_shape(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["PETR4", "VALE3"])
        fin = r["sections"]["financials"]
        assert "Receita Líquida" in fin["columns"]
        assert "ROE" in fin["columns"]
        rec_idx = fin["columns"].index("Receita Líquida")
        assert fin["rows"][0][rec_idx] == 400_000_000_000

    def test_dividends_section_shape(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["PETR4", "VALE3"])
        div = r["sections"]["dividends"]
        assert "Eventos (B3)" in div["columns"]
        assert "Dividendos (últ ano)" in div["columns"]
        ev_idx = div["columns"].index("Eventos (B3)")
        assert div["rows"][0][ev_idx] == 3  # PETR4 had 3 events

    def test_formats_per_column(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["PETR4", "VALE3"])
        val = r["sections"]["valuation"]
        assert val["formats"]["Ticker"] == "text"
        assert val["formats"]["P/L"] == "num"
        assert val["formats"]["Market Cap"] == "brl"
        assert val["formats"]["Div Yield"] == "pct"

    def test_best_effort_one_ticker_fails(self, monkeypatch):
        """If valuation fails for one ticker, comparison still returns the others."""
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": {"status": "error", "error": "no price"}},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        # VALE3's valuation cells are None (price lookup failed)
        val = r["sections"]["valuation"]
        price_idx = val["columns"].index("Preço")
        assert val["rows"][0][price_idx] == 38.5      # PETR4 OK
        assert val["rows"][1][price_idx] is None       # VALE3 failed
        # errors list captured VALE3's valuation failure
        assert any("valuation" in e for e in r["errors"])
        assert len(r["errors"]) == 1

    def test_uppercases_tickers(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = side_by_side(tickers=["petr4", "vale3"])
        assert r["tickers"] == ["PETR4", "VALE3"]


# ── summary mode ─────────────────────────────────────────────────────────────

class TestSummary:
    def test_basic_shape(self, monkeypatch):
        _mock_skills(monkeypatch,
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

    def test_summary_has_kpi_values(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        r = summary(tickers=["PETR4", "VALE3"])
        sec = r["sections"][0]
        pl_idx = sec["columns"].index("P/L")
        # PETR4 P/L = 8.2, VALE3 P/L = 6.5
        assert sec["rows"][0][pl_idx] == 8.2
        assert sec["rows"][1][pl_idx] == 6.5


# ── Dividend metric extraction ───────────────────────────────────────────────

class TestExtractDividendMetrics:
    def test_extracts_event_count_and_dpa_avg(self):
        sections = {"recent_events": {"status": "ok", "count": 3,
                                      "events": [{"rate": 1.5}, {"rate": 2.0}, {"rate": 1.0}]}}
        m = _extract_dividend_metrics(sections)
        assert m["event_count"] == 3
        assert m["b3_dpa_avg"] == pytest.approx(1.5)  # (1.5+2.0+1.0)/3

    def test_extracts_annual_totals(self):
        sections = {"annual_trend": {"status": "ok", "periods": [
            {"accounts": {"7.08.04": {"valor_brl": 30_000_000_000},
                          "7.08.04.01": {"valor_brl": 5_000_000_000},
                          "7.08.04.02": {"valor_brl": 25_000_000_000}}}]}}
        m = _extract_dividend_metrics(sections)
        assert m["annual_total"] == 30_000_000_000
        assert m["annual_jcp"] == 5_000_000_000
        assert m["annual_dividendos"] == 25_000_000_000

    def test_empty_sections_return_nones(self):
        m = _extract_dividend_metrics({})
        assert m["event_count"] is None
        assert m["annual_total"] is None


# ── Route dispatch ───────────────────────────────────────────────────────────

class TestRoute:
    def test_route_no_mode_errors(self):
        from skills.cvm.comparison import route
        r = route()
        assert r["status"] == "error"
        assert "mode" in r["error"]

    def test_route_unknown_mode_errors(self):
        from skills.cvm.comparison import route
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]

    def test_route_side_by_side(self, monkeypatch):
        _mock_skills(monkeypatch,
                     {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                     {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                     {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        from skills.cvm.comparison import route
        r = route(mode="side_by_side", tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"


# ── Growth mode ──────────────────────────────────────────────────────────────

FIN_QUARTERLY_SUZB3 = {
    "status": "ok", "company": "SUZANO", "period_type": "quarterly",
    "periods": [
        {"period": "1T2024", "year": 2024, "quarter": 1,
         "metrics": {"receita_liquida": 100, "ebitda": 30, "lucro_liquido": 15}},
        {"period": "2T2024", "year": 2024, "quarter": 2,
         "metrics": {"receita_liquida": 110, "ebitda": 33, "lucro_liquido": 16}},
        {"period": "3T2024", "year": 2024, "quarter": 3,
         "metrics": {"receita_liquida": 120, "ebitda": 36, "lucro_liquido": 18}},
        {"period": "4T2024", "year": 2024, "quarter": 4,
         "metrics": {"receita_liquida": 130, "ebitda": 39, "lucro_liquido": 20}},
        {"period": "1T2025", "year": 2025, "quarter": 1,
         "metrics": {"receita_liquida": 140, "ebitda": 42, "lucro_liquido": 22}},
    ],
    "ttm": {"status": "ok", "period_range": "2T2024–1T2025",
            "metrics": {}, "ratios": {"marg_ebitda": 0.28, "roe": 0.15}},
}


class TestGrowthMode:
    def test_growth_requires_tickers(self):
        r = growth()
        assert r["status"] == "error"

    def test_growth_requires_min_two(self):
        r = growth(tickers=["SUZB3"])
        assert r["status"] == "error"

    def test_growth_basic_shape(self, monkeypatch):
        def fake_quarterly(company="", periods=8, consolidado=1):
            if company == "SUZB3":
                return FIN_QUARTERLY_SUZB3
            return {"status": "ok", "company": company, "period_type": "quarterly",
                    "periods": FIN_QUARTERLY_SUZB3["periods"],
                    "ttm": FIN_QUARTERLY_SUZB3["ttm"]}
        monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)
        r = growth(tickers=["SUZB3", "KLBN11"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["SUZB3", "KLBN11"]
        assert len(r["sections"]) == 1
        sec = r["sections"][0]
        assert "Receita QoQ" in sec["columns"]
        assert "Receita YoY" in sec["columns"]
        assert "ROE (TTM)" in sec["columns"]
        assert len(sec["rows"]) == 2

    def test_growth_qoq_computation(self, monkeypatch):
        """QoQ = (latest - prior) / |prior|."""
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)
        r = growth(tickers=["SUZB3", "VALE3"])
        sec = r["sections"][0]
        qoq_idx = sec["columns"].index("Receita QoQ")
        # latest=1T2025=140, prior=4T2024=130 -> (140-130)/130 = 0.0769...
        assert sec["rows"][0][qoq_idx] == pytest.approx((140 - 130) / 130, rel=1e-3)

    def test_growth_yoy_computation(self, monkeypatch):
        """YoY = (latest - same_q_prior_year) / |same_q_prior_year|."""
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)
        r = growth(tickers=["SUZB3", "VALE3"])
        sec = r["sections"][0]
        yoy_idx = sec["columns"].index("Receita YoY")
        # latest=1T2025=140, yoy_prior=1T2024=100 (4 periods back) -> (140-100)/100 = 0.4
        assert sec["rows"][0][yoy_idx] == pytest.approx(0.4, rel=1e-3)

    def test_growth_ttm_ratios(self, monkeypatch):
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)
        r = growth(tickers=["SUZB3", "VALE3"])
        sec = r["sections"][0]
        roe_idx = sec["columns"].index("ROE (TTM)")
        assert sec["rows"][0][roe_idx] == 0.15  # from ttm.ratios.roe


class TestPctChange:
    def test_positive_growth(self):
        assert _pct_change(120, 100) == pytest.approx(0.2)

    def test_negative_growth(self):
        assert _pct_change(80, 100) == pytest.approx(-0.2)

    def test_zero_prev_is_none(self):
        assert _pct_change(100, 0) is None

    def test_negative_prev_is_none(self):
        """Sign-change guard: negative base -> None (can't compute meaningful %)."""
        assert _pct_change(36, -1) is None

    def test_sign_change_profit_to_loss_is_none(self):
        """Profit -> loss sign change: +R$1M -> -R$3M = -400% (noise)."""
        assert _pct_change(-3, 1) is None

    def test_sign_change_loss_to_profit_is_none(self):
        """Loss -> profit sign change: -R$1M -> +R$3M (noise)."""
        assert _pct_change(3, -1) is None

    def test_extreme_growth_is_shown(self):
        """Extreme but same-sign growth is NOT suppressed — LLM can judge."""
        assert _pct_change(700, 100) == pytest.approx(6.0)  # 600%

    def test_none_values(self):
        assert _pct_change(None, 100) is None
        assert _pct_change(100, None) is None

    def test_large_same_sign_growth(self):
        """Large same-sign growth passes through (not noise — just big)."""
        assert _pct_change(600, 100) == pytest.approx(5.0)  # 500%
        assert _pct_change(499, 100) == pytest.approx(3.99)  # 399%
