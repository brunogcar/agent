"""Tests for report_ops/adapters/ — skill JSON → table data adapters.

Covers: registry auto-discovery (12 adapters), the financials/valuation/
shareholders/dividends adapters, error handling, and the _kv_section helper.
"""
from __future__ import annotations

import pytest

# Importing the package triggers @register_adapter decorators
from tools.report_ops import adapters
from tools.report_ops.adapters import (
    ADAPTERS, apply_adapter, list_adapters, register_adapter,
    _ok, _error_table, _kv_section, _safe_num,
)


# ── Synthetic skill results ──────────────────────────────────────────────────

FINANCIALS_QUARTERLY = {
    "status": "ok", "company": "PETROBRAS", "period_type": "quarterly",
    "periods": [
        {"period": "1T2025",
         "metrics": {"receita_liquida": 100_000, "lucro_bruto": 30_000,
                     "ebit": 20_000, "ebitda": 25_000, "lucro_liquido": 15_000,
                     "fco": 22_000, "ativo_total": 500_000, "patrimonio_liquido": 200_000},
         "ratios": {"marg_bruta": 0.30, "marg_ebitda": 0.25,
                    "marg_liquida": 0.15, "roe": 0.18}},
        {"period": "2T2025",
         "metrics": {"receita_liquida": 120_000, "lucro_bruto": 36_000,
                     "ebit": 24_000, "ebitda": 30_000, "lucro_liquido": 18_000,
                     "fco": 26_000, "ativo_total": 520_000, "patrimonio_liquido": 210_000},
         "ratios": {"marg_bruta": 0.30, "marg_ebitda": 0.25,
                    "marg_liquida": 0.15, "roe": 0.20}},
    ],
}

VALUATION_RATIOS = {
    "status": "ok", "ticker": "PETR4",
    "ratios": {"price": 38.5, "p_l": 8.2, "p_vpa": 1.9, "ev_ebitda": 4.5,
               "dividend_yield": 0.12, "market_cap": 500_000_000_000,
               "total_shares": 13_000_000_000, "eps": 4.7, "vpa": 20.1},
    "sources": {},
}

SHAREHOLDERS = {
    "status": "ok", "company": "PETROBRAS", "cnpj": "33.000.167/0001-01",
    "data_referencia": "2024-12-31",
    "shareholders": [
        {"acionista": "União", "cpf_cnpj": "00000000000000", "tipo_pessoa": "PJ",
         "controlador": 1, "pct_on": 36.7, "pct_pn": 10.0, "pct_total": 28.3,
         "qtd_on": 1000, "qtd_pn": 200, "qtd_total": 1200},
    ],
}

DIVIDENDS_HISTORY = {
    "status": "ok", "ticker": "PETR4", "count": 2,
    "dividends": [
        {"approved_on": "2025-04-01", "last_date_prior": "2025-04-10",
         "payment_date": "2025-05-10", "rate": 1.55, "label": "Dividendo",
         "related_to": "1T2025"},
    ],
}


class TestRegistry:
    def test_adapters_registered(self):
        names = list_adapters()
        assert len(names) == 68

    def test_expected_adapter_names(self):
        expected = {
            "financials_quarterly", "financials_annual", "financials_summary",
            "financials_quarterly_chart", "financials_dashboard",
            "valuation_ratios", "valuation_summary", "valuation_dashboard",
            "shareholders_shareholders", "shareholders_free_float",
            "shareholders_equity_structure", "shareholders_summary",
            "dividends_history", "dividends_annual", "dividends_summary",
            "comparison_side_by_side", "comparison_summary", "comparison_growth",
            "comparison_dashboard",
            "cotahist_close_chart",
            "cotahist_candlestick_chart",
            "screener_sector",
            "insider_history", "insider_by_role", "insider_summary",
            "governance_practices", "governance_score", "governance_by_chapter",
            "historical_lpa_chart", "historical_vpa_chart", "historical_dpa_chart",
            "historical_rps_chart", "historical_roe_chart",
            "historical_roa_chart", "historical_gross_margin_chart",
            "historical_operating_margin_chart", "historical_roic_chart",
            "historical_ev_ebitda_chart",
            "historical_net_margin_chart", "historical_ebitda_margin_chart",
            "historical_debt_equity_chart", "historical_net_debt_ebitda_chart",
            "historical_asset_turnover_chart",
            "historical_capex_revenue_chart", "historical_current_ratio_chart",
            "historical_p_ebit_chart", "historical_p_fco_chart",
            "historical_p_fcf_chart", "historical_graham_number_chart",
            "historical_effective_tax_rate_chart",
            "historical_ev_sales_chart", "historical_ev_fcf_chart",
            "historical_cash_ratio_chart", "historical_ocf_margin_chart",
            "historical_fcf_margin_chart", "historical_working_capital_chart",
            "historical_cash_flow_to_debt_chart", "historical_retention_ratio_chart",
            "historical_sustainable_growth_chart",
            "historical_quick_ratio_chart", "historical_interest_coverage_chart",
            "historical_inventory_turnover_chart", "historical_receivables_turnover_chart",
            "historical_fixed_asset_turnover_chart", "historical_price_to_tangible_book_chart",
            "historical_summary",
            "backtest",
            "backtest_dashboard",
        }
        assert expected == set(list_adapters())

    def test_duplicate_registration_raises(self):
        with pytest.raises(ValueError, match="Duplicate adapter"):
            @register_adapter("financials_quarterly")
            def _dup(result): return {}

    def test_apply_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            apply_adapter("nope", {"status": "ok"})

    def test_apply_non_dict_raises(self):
        with pytest.raises(ValueError, match="dict"):
            apply_adapter("financials_quarterly", ["not", "a", "dict"])


class TestHelpers:
    def test_ok_true_for_ok(self):
        assert _ok({"status": "ok"}) is True

    def test_ok_false_for_errors(self):
        assert _ok({"status": "not_found"}) is False
        assert _ok({"status": "not_synced"}) is False
        assert _ok({}) is False
        assert _ok(None) is False

    def test_error_table_shape(self):
        out = _error_table({"status": "not_synced", "error": "db missing"})
        assert out["sections"][0]["columns"] == ["Status", "Detail"]
        assert out["sections"][0]["rows"] == [["not_synced", "db missing"]]

    def test_kv_section_preformats_values(self):
        sec = _kv_section("Indicators", [("Market Cap", 1_000_000, "brl")])
        assert sec["columns"] == ["Indicador", "Valor"]
        # value pre-formatted via apply_fmt -> "R$ 1,00 M"
        assert sec["rows"] == [["Market Cap", "R$ 1,00 M"]]
        assert sec["formats"]["Valor"] == "text"

    def test_safe_num_passthrough(self):
        assert _safe_num(42) == 42
        assert _safe_num(3.14) == 3.14
        assert _safe_num(None) is None

    def test_safe_num_coerces_numeric_string(self):
        assert _safe_num("42") == 42
        assert _safe_num("3,14") == 3.14


class TestFinancialsAdapters:
    def test_quarterly_reverses_to_newest_first(self):
        out = apply_adapter("financials_quarterly", FINANCIALS_QUARTERLY)
        assert out["company"] == "PETROBRAS"
        rows = out["sections"][0]["rows"]
        # skill periods are oldest-first [1T, 2T]; adapter reverses -> [2T, 1T]
        assert rows[0][0] == "2T2025"
        assert rows[1][0] == "1T2025"

    def test_quarterly_kpis_from_latest_period(self):
        out = apply_adapter("financials_quarterly", FINANCIALS_QUARTERLY)
        # latest = 2T2025 -> receita 120000
        labels = [k["label"] for k in out["kpis"]]
        assert "Receita Líquida" in labels
        receita_kpi = next(k for k in out["kpis"] if k["label"] == "Receita Líquida")
        assert receita_kpi["value"] == 120_000
        assert receita_kpi["format"] == "brl"

    def test_quarterly_has_money_and_pct_formats(self):
        out = apply_adapter("financials_quarterly", FINANCIALS_QUARTERLY)
        fmts = out["sections"][0]["formats"]
        assert fmts["Receita Líquida"] == "brl"
        assert fmts["EBITDA"] == "brl"
        assert fmts["Marg. EBITDA"] == "pct"
        assert fmts["ROE"] == "pct"

    def test_quarterly_error_renders_status_table(self):
        out = apply_adapter("financials_quarterly", {"status": "not_found", "error": "no data"})
        assert out["sections"][0]["title"] == "Quarterly Financials"
        assert out["sections"][0]["rows"][0] == ["not_found", "no data"]

    def test_annual_uses_first_period_as_latest(self):
        annual = {"status": "ok", "company": "X", "period_type": "annual",
                  "periods": [{"period": "2024", "metrics": {"receita_liquida": 1_000_000},
                               "ratios": {"roe": 0.15}}]}
        out = apply_adapter("financials_annual", annual)
        # annual is newest-first in the skill; adapter keeps order
        assert out["sections"][0]["rows"][0][0] == "2024"

    def test_summary_combines_kpis_trend_and_detail(self):
        summary = {"status": "ok", "company": "X", "sections": {
            "latest_annual": {"period": "2024", "metrics": {"receita_liquida": 1_000_000, "ebitda": 300_000},
                              "ratios": {"marg_ebitda": 0.30}},
            "quarterly_trend": FINANCIALS_QUARTERLY["periods"],
        }}
        out = apply_adapter("financials_summary", summary)
        # KPIs from latest_annual
        assert any(k["label"] == "Receita Líquida" for k in out["kpis"])
        # at least 2 sections: detail (KV) + quarterly trend
        assert len(out["sections"]) >= 2


class TestValuationAdapters:
    def test_ratios_kpis_present(self):
        out = apply_adapter("valuation_ratios", VALUATION_RATIOS)
        labels = [k["label"] for k in out["kpis"]]
        assert "Preço" in labels and "P/L" in labels and "Market Cap" in labels

    def test_ratios_section_is_indicator_table(self):
        out = apply_adapter("valuation_ratios", VALUATION_RATIOS)
        sec = out["sections"][0]
        assert sec["columns"] == ["Indicador", "Valor"]
        # values pre-formatted (KV section)
        assert sec["formats"]["Valor"] == "text"

    def test_ratios_market_cap_formatted(self):
        out = apply_adapter("valuation_ratios", VALUATION_RATIOS)
        rows = out["sections"][0]["rows"]
        mcap = next(r for r in rows if r[0] == "Market Cap")
        assert mcap[1] == "R$ 500,00 B"

    def test_ratios_error_renders_status(self):
        out = apply_adapter("valuation_ratios", {"status": "error", "error": "no price"})
        assert out["sections"][0]["rows"][0] == ["error", "no price"]

    def test_summary_has_availability_section(self):
        summary = dict(VALUATION_RATIOS)
        summary["data_availability"] = {"price": "ok", "dfp_annual": "ok", "fre_shares": "missing"}
        out = apply_adapter("valuation_summary", summary)
        titles = [s["title"] for s in out["sections"]]
        assert any("Availability" in t for t in titles)


class TestShareholdersAdapters:
    def test_shareholders_table_shape(self):
        out = apply_adapter("shareholders_shareholders", SHAREHOLDERS)
        sec = out["sections"][0]
        assert "% Total" in sec["columns"]
        assert sec["formats"]["% Total"] == "pct_raw"  # CVM stores % as plain numbers
        assert sec["formats"]["Qtde Total"] == "int"
        assert sec["rows"][0][0] == "União"

    def test_shareholders_error(self):
        out = apply_adapter("shareholders_shareholders", {"status": "not_found", "error": "x"})
        assert out["sections"][0]["title"] == "Shareholders"


class TestDividendsAdapters:
    def test_history_table_shape(self):
        out = apply_adapter("dividends_history", DIVIDENDS_HISTORY)
        sec = out["sections"][0]
        assert "Valor/Ação" in sec["columns"]
        assert sec["formats"]["Valor/Ação"] == "brl_full"  # per-share -> full BRL
        assert out["kpis"][0]["label"] == "Total Eventos"
        assert out["kpis"][0]["value"] == 2

    def test_history_error(self):
        out = apply_adapter("dividends_history", {"status": "not_synced", "error": "db"})
        assert out["sections"][0]["rows"][0] == ["not_synced", "db"]


# ── Comparison skill results ─────────────────────────────────────────────────

COMPARISON_SIDE_BY_SIDE = {
    "status": "ok",
    "tickers": ["PETR4", "VALE3"],
    "sections": {
        "valuation": {
            "title": "Valuation Ratios",
            "columns": ["Ticker", "P/L", "Market Cap"],
            "rows": [["PETR4", 8.2, 500_000_000_000], ["VALE3", 6.5, 300_000_000_000]],
            "formats": {"Ticker": "text", "P/L": "num", "Market Cap": "brl"},
        },
        "financials": {
            "title": "Financial Metrics (latest annual)",
            "columns": ["Ticker", "Receita Líquida", "ROE"],
            "rows": [["PETR4", 400_000_000_000, 0.15], ["VALE3", 300_000_000_000, 0.14]],
            "formats": {"Ticker": "text", "Receita Líquida": "brl", "ROE": "pct"},
        },
        "dividends": {
            "title": "Dividend Metrics",
            "columns": ["Ticker", "Eventos (B3)"],
            "rows": [["PETR4", 3], ["VALE3", 2]],
            "formats": {"Ticker": "text", "Eventos (B3)": "int"},
        },
    },
    "errors": [],
}

COMPARISON_SUMMARY = {
    "status": "ok",
    "tickers": ["PETR4", "VALE3"],
    "sections": [{
        "title": "Quick Compare",
        "columns": ["Ticker", "P/L", "ROE", "Receita Líquida"],
        "rows": [["PETR4", 8.2, 0.15, 400_000_000_000], ["VALE3", 6.5, 0.14, 300_000_000_000]],
        "formats": {"Ticker": "text", "P/L": "num", "ROE": "pct", "Receita Líquida": "brl"},
    }],
    "errors": [],
}


class TestComparisonAdapters:
    def test_side_by_side_passes_through_3_sections(self):
        out = apply_adapter("comparison_side_by_side", COMPARISON_SIDE_BY_SIDE)
        assert len(out["sections"]) == 3
        titles = [s["title"] for s in out["sections"]]
        assert "Valuation Ratios" in titles
        assert "Financial Metrics (latest annual)" in titles
        assert "Dividend Metrics" in titles
        # company field joins tickers
        assert "PETR4" in out["company"] and "VALE3" in out["company"]

    def test_side_by_side_preserves_formats(self):
        out = apply_adapter("comparison_side_by_side", COMPARISON_SIDE_BY_SIDE)
        val = out["sections"][0]
        assert val["formats"]["P/L"] == "num"
        assert val["formats"]["Market Cap"] == "brl"

    def test_side_by_side_error_renders_status(self):
        out = apply_adapter("comparison_side_by_side",
                            {"status": "error", "error": "no tickers"})
        assert out["sections"][0]["rows"][0] == ["error", "no tickers"]

    def test_side_by_side_empty_sections_errors(self):
        out = apply_adapter("comparison_side_by_side",
                            {"status": "ok", "tickers": ["X"], "sections": {}})
        assert out["sections"][0]["title"] == "Comparison"

    def test_summary_single_section_with_kpis(self):
        out = apply_adapter("comparison_summary", COMPARISON_SUMMARY)
        assert len(out["sections"]) == 1
        assert out["sections"][0]["title"] == "Quick Compare"
        # KPI strip: one per ticker, showing its P/L
        assert len(out["kpis"]) == 2
        labels = [k["label"] for k in out["kpis"]]
        assert labels == ["PETR4", "VALE3"]
        # P/L values pre-formatted as "num" spec
        assert out["kpis"][0]["value"] == "8,20"
        assert out["kpis"][1]["value"] == "6,50"

    def test_summary_error_renders_status(self):
        out = apply_adapter("comparison_summary",
                            {"status": "error", "error": "failed"})
        assert out["sections"][0]["rows"][0] == ["error", "failed"]


# ── Growth comparison + chart adapter ────────────────────────────────────────

COMPARISON_GROWTH = {
    "status": "ok",
    "tickers": ["SUZB3", "KLBN11"],
    "sections": [{
        "title": "Growth Metrics (QoQ + YoY + TTM)",
        "columns": ["Ticker", "Receita QoQ", "Receita YoY", "ROE (TTM)"],
        "rows": [["SUZB3", 0.15, 0.20, 0.30], ["KLBN11", -0.05, 0.10, 0.12]],
        "formats": {"Ticker": "text", "Receita QoQ": "pct_raw",
                    "Receita YoY": "pct_raw", "ROE (TTM)": "pct"},
    }],
    "errors": [],
}

FINANCIALS_QUARTERLY_FOR_CHART = {
    "status": "ok", "company": "PETR4", "period_type": "quarterly",
    "periods": [
        {"period": "1T2025", "year": 2025, "quarter": 1,
         "metrics": {"receita_liquida": 100, "ebitda": 25, "lucro_liquido": 15}},
        {"period": "2T2025", "year": 2025, "quarter": 2,
         "metrics": {"receita_liquida": 120, "ebitda": 30, "lucro_liquido": 18}},
    ],
    "ttm": {"status": "insufficient_data"},
}


class TestComparisonGrowthAdapter:
    def test_growth_passes_through_section(self):
        out = apply_adapter("comparison_growth", COMPARISON_GROWTH)
        assert len(out["sections"]) == 1
        assert out["sections"][0]["title"] == "Growth Metrics (QoQ + YoY + TTM)"
        assert "SUZB3" in out["company"] and "KLBN11" in out["company"]

    def test_growth_error_renders_status(self):
        out = apply_adapter("comparison_growth",
                            {"status": "error", "error": "no data"})
        assert out["sections"][0]["rows"][0] == ["error", "no data"]


class TestFinancialsChartAdapter:
    def test_chart_adapter_multi_series(self):
        out = apply_adapter("financials_quarterly_chart", FINANCIALS_QUARTERLY_FOR_CHART)
        assert "x" in out and "datasets" in out
        # x labels oldest-first
        assert out["x"] == ["1T2025", "2T2025"]
        # 3 datasets (Receita, EBITDA, Lucro)
        assert len(out["datasets"]) == 3
        labels = [d["label"] for d in out["datasets"]]
        assert labels == ["Receita Líquida", "EBITDA", "Lucro Líquido"]
        # values landed
        assert out["datasets"][0]["data"] == [100, 120]
        assert out["datasets"][1]["data"] == [25, 30]

    def test_chart_adapter_error_returns_empty(self):
        out = apply_adapter("financials_quarterly_chart",
                            {"status": "not_synced", "error": "db"})
        assert out["x"] == []
        assert out["y"] == []


# ── COTAHIST chart adapter ───────────────────────────────────────────────────

COTAHIST_RESULT = {
    "status": "ok",
    "count": 3,
    "rows": [
        {"refdate": "2025-07-03", "close": 38.5},
        {"refdate": "2025-07-02", "close": 38.2},
        {"refdate": "2025-07-01", "close": 38.0},
    ],
}


class TestCotahistChartAdapter:
    def test_close_chart_from_result(self):
        out = apply_adapter("cotahist_close_chart", COTAHIST_RESULT)
        assert "x" in out and "y" in out
        # sorted oldest-first
        assert out["x"] == ["2025-07-01", "2025-07-02", "2025-07-03"]
        assert out["y"] == [38.0, 38.2, 38.5]

    def test_close_chart_error_result(self):
        out = apply_adapter("cotahist_close_chart",
                            {"status": "not_synced", "error": "db missing"})
        assert out["x"] == []
        assert "db missing" in out.get("_error", "")

    def test_close_chart_empty_rows(self):
        out = apply_adapter("cotahist_close_chart",
                            {"status": "ok", "count": 0, "rows": []})
        assert out["x"] == []
        assert "no rows" in out.get("_error", "")


# ── COTAHIST candlestick adapter ─────────────────────────────────────────────

COTAHIST_OHLC = {
    "status": "ok", "count": 3,
    "rows": [
        {"refdate": "2025-07-03", "open": 38.5, "high": 39.0, "low": 38.2, "close": 38.8},
        {"refdate": "2025-07-02", "open": 38.0, "high": 38.5, "low": 37.8, "close": 38.2},
        {"refdate": "2025-07-01", "open": 37.5, "high": 38.0, "low": 37.3, "close": 37.9},
    ],
}


class TestCotahistCandlestickAdapter:
    def test_candlestick_from_result(self):
        out = apply_adapter("cotahist_candlestick_chart", COTAHIST_OHLC)
        assert out.get("_candlestick") is True
        ohlc = out.get("ohlc_data") or []
        assert len(ohlc) == 3
        # sorted oldest-first
        assert ohlc[0]["t"] == "2025-07-01"
        assert ohlc[0]["o"] == 37.5
        assert ohlc[2]["c"] == 38.8

    def test_candlestick_error_result(self):
        out = apply_adapter("cotahist_candlestick_chart",
                            {"status": "not_synced", "error": "db missing"})
        assert out.get("_candlestick") is not True
        assert "db missing" in out.get("_error", "")

    def test_candlestick_skips_incomplete_rows(self):
        data = {"status": "ok", "rows": [
            {"refdate": "2025-07-01", "open": 37.5, "high": 38.0, "low": 37.3, "close": 37.9},
            {"refdate": "2025-07-02", "open": None, "high": 38.5, "low": 38.1, "close": 38.2},
        ]}
        out = apply_adapter("cotahist_candlestick_chart", data)
        ohlc = out.get("ohlc_data") or []
        assert len(ohlc) == 1  # second row skipped (open=None)


# ── Historical adapters ─────────────────────────────────────────────────────

class TestHistoricalLpaChartAdapter:
    def test_lpa_chart_dual_dataset(self):
        """lpa_chart should produce TWO datasets: LPA (per-share) + P/L (ratio)."""
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-01-15", "lpa": 8.46, "pe": 4.5},
                {"date": "2024-02-15", "lpa": 8.46, "pe": None},  # gap
                {"date": "2024-03-15", "lpa": 8.88, "pe": 5.2},
            ],
        }
        out = apply_adapter("historical_lpa_chart", data)
        assert out["x"] == ["2024-01-15", "2024-02-15", "2024-03-15"]
        assert len(out["datasets"]) == 2  # dual dataset
        # Dataset 0 = per-share value (LPA) on left axis
        assert out["datasets"][0]["label"] == "LPA"
        assert out["datasets"][0]["data"] == [8.46, 8.46, 8.88]
        assert out["datasets"][0]["yAxisID"] == "y"  # left axis
        # Dataset 1 = ratio (P/L) on right axis
        assert out["datasets"][1]["label"] == "P/L"
        assert out["datasets"][1]["data"] == [4.5, None, 5.2]
        assert out["datasets"][1]["yAxisID"] == "y1"  # right axis (dual-axis)

    def test_lpa_chart_error_result(self):
        out = apply_adapter("historical_lpa_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_lpa_chart_empty_series(self):
        out = apply_adapter("historical_lpa_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalVpaChartAdapter:
    def test_vpa_chart_dual_dataset(self):
        """vpa_chart should produce TWO datasets: VPA (per-share) + P/VPA (ratio)."""
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-01-15", "vpa": 23.08, "pvpa": 1.45},
                {"date": "2024-02-15", "vpa": 23.08, "pvpa": None},  # gap
                {"date": "2024-03-15", "vpa": 23.85, "pvpa": 1.52},
            ],
        }
        out = apply_adapter("historical_vpa_chart", data)
        assert out["x"] == ["2024-01-15", "2024-02-15", "2024-03-15"]
        assert len(out["datasets"]) == 2  # dual dataset
        # Dataset 0 = per-share value (VPA) on left axis
        assert out["datasets"][0]["label"] == "VPA"
        assert out["datasets"][0]["data"] == [23.08, 23.08, 23.85]
        assert out["datasets"][0]["yAxisID"] == "y"  # left axis
        # Dataset 1 = ratio (P/VPA) on right axis
        assert out["datasets"][1]["label"] == "P/VPA"
        assert out["datasets"][1]["data"] == [1.45, None, 1.52]
        assert out["datasets"][1]["yAxisID"] == "y1"  # right axis (dual-axis)

    def test_vpa_chart_error_result(self):
        out = apply_adapter("historical_vpa_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_vpa_chart_empty_series(self):
        out = apply_adapter("historical_vpa_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalSummaryAdapter:
    def test_summary_lpa_metric(self):
        """Summary adapter with metric=lpa should render LPA + P/L + TTM Earnings rows."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "lpa",
            "per_share_label": "LPA",
            "ratio_label": "P/L",
            "current": {
                "date": "2024-07-26", "lpa": 10.35, "pe": 4.75, "price": 38.5,
                "ttm_earnings": 134e9, "shares": 13e9,
            },
            "averages": {"1y": 6.2, "3y": 7.5, "5y": 8.1},
            "range": {"min": 3.1, "max": 12.5},
            "percentile": 25.0,
            "interpretation": "cheap (below 25th percentile of history)",
            "data_points": 1100,
        }
        out = apply_adapter("historical_summary", data)
        assert out["company"] == "PETR4"
        # KPI strip — should have both LPA and P/L
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current LPA" in kpi_labels
        assert "Current P/L" in kpi_labels
        assert "Percentile" in kpi_labels
        # Summary table — should mention P/L, LPA, TTM Earnings
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "P/L" in rows_text
        assert "LPA" in rows_text
        assert "TTM Earnings" in rows_text

    def test_summary_vpa_metric(self):
        """Summary adapter with metric=vpa should render VPA + P/VPA + PL rows."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "vpa",
            "per_share_label": "VPA",
            "ratio_label": "P/VPA",
            "current": {
                "date": "2024-07-26", "vpa": 23.85, "pvpa": 1.45, "price": 38.5,
                "pl": 350e9, "shares": 13e9,
            },
            "averages": {"1y": 1.5, "3y": 1.6, "5y": 1.7},
            "range": {"min": 0.9, "max": 2.1},
            "percentile": 30.0,
            "interpretation": "fair (between 25th-75th percentile of history)",
            "data_points": 1100,
        }
        out = apply_adapter("historical_summary", data)
        # KPI strip — should have both VPA and P/VPA
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current VPA" in kpi_labels
        assert "Current P/VPA" in kpi_labels
        # Summary table — should mention VPA, P/VPA, Patrimônio Líquido
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "VPA" in rows_text
        assert "P/VPA" in rows_text
        assert "Patrim" in rows_text  # "Patrimônio Líquido"
        # Should NOT have TTM Earnings row for vpa metric
        assert "TTM Earnings" not in rows_text

    def test_summary_error_result(self):
        out = apply_adapter("historical_summary",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table


class TestHistoricalDpaChartAdapter:
    def test_dpa_chart_dual_dataset_dual_axis(self):
        """dpa_chart should produce TWO datasets with yAxisID for dual-axis."""
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-01-15", "dpa": 1.85, "dy": 0.052},
                {"date": "2024-02-15", "dpa": 1.85, "dy": None},  # gap
                {"date": "2024-03-15", "dpa": 1.90, "dy": 0.050},
            ],
        }
        out = apply_adapter("historical_dpa_chart", data)
        assert out["x"] == ["2024-01-15", "2024-02-15", "2024-03-15"]
        assert len(out["datasets"]) == 2  # dual dataset
        # Dataset 0 = per-share value (DPA) on left axis
        assert out["datasets"][0]["label"] == "DPA"
        assert out["datasets"][0]["data"] == [1.85, 1.85, 1.90]
        assert out["datasets"][0]["yAxisID"] == "y"  # left axis
        # Dataset 1 = ratio (Div Yield) on right axis
        assert out["datasets"][1]["label"] == "Div Yield"
        assert out["datasets"][1]["data"] == [0.052, None, 0.050]
        assert out["datasets"][1]["yAxisID"] == "y1"  # right axis (dual-axis)

    def test_dpa_chart_error_result(self):
        out = apply_adapter("historical_dpa_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_dpa_chart_empty_series(self):
        out = apply_adapter("historical_dpa_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalSummaryDpaMetric:
    def test_summary_dpa_metric(self):
        """Summary adapter with metric=dpa should render DPA + Div Yield + TTM Earnings rows."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "dpa",
            "per_share_label": "DPA",
            "ratio_label": "Div Yield",
            "current": {
                "date": "2024-07-26", "dpa": 1.85, "dy": 0.048, "price": 38.5,
                "ttm_earnings": 134e9, "shares": 13e9,
            },
            "averages": {"1y": 0.045, "3y": 0.042, "5y": 0.040},
            "range": {"min": 0.030, "max": 0.055},
            "percentile": 75.0,
            "interpretation": "expensive (above 75th percentile of history)",
            "data_points": 1100,
        }
        out = apply_adapter("historical_summary", data)
        # KPI strip — should have both DPA and Div Yield
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current DPA" in kpi_labels
        assert "Current Div Yield" in kpi_labels
        # Summary table — should mention DPA, Div Yield, TTM Earnings
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "DPA" in rows_text
        assert "Div Yield" in rows_text
        assert "TTM Earnings" in rows_text  # dpa uses earnings for payout


class TestHistoricalRpsChartAdapter:
    def test_rps_chart_dual_dataset_dual_axis(self):
        """rps_chart should produce TWO datasets with yAxisID for dual-axis."""
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-01-15", "rps": 19.23, "psr": 1.82},
                {"date": "2024-02-15", "rps": 19.23, "psr": None},  # gap
                {"date": "2024-03-15", "rps": 20.00, "psr": 1.90},
            ],
        }
        out = apply_adapter("historical_rps_chart", data)
        assert out["x"] == ["2024-01-15", "2024-02-15", "2024-03-15"]
        assert len(out["datasets"]) == 2  # dual dataset
        # Dataset 0 = per-share value (RPS) on left axis
        assert out["datasets"][0]["label"] == "RPS"
        assert out["datasets"][0]["data"] == [19.23, 19.23, 20.00]
        assert out["datasets"][0]["yAxisID"] == "y"  # left axis
        # Dataset 1 = ratio (PSR) on right axis
        assert out["datasets"][1]["label"] == "PSR"
        assert out["datasets"][1]["data"] == [1.82, None, 1.90]
        assert out["datasets"][1]["yAxisID"] == "y1"  # right axis (dual-axis)

    def test_rps_chart_error_result(self):
        out = apply_adapter("historical_rps_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_rps_chart_empty_series(self):
        out = apply_adapter("historical_rps_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalSummaryRpsMetric:
    def test_summary_rps_metric(self):
        """Summary adapter with metric=rps should render RPS + PSR + TTM Revenue rows."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "rps",
            "per_share_label": "RPS",
            "ratio_label": "PSR",
            "current": {
                "date": "2024-07-26", "rps": 21.54, "psr": 1.79, "price": 38.5,
                "ttm_rev": 280e9, "shares": 13e9,
            },
            "averages": {"1y": 1.85, "3y": 1.92, "5y": 2.10},
            "range": {"min": 1.50, "max": 2.80},
            "percentile": 40.0,
            "interpretation": "fair (between 25th-75th percentile of history)",
            "data_points": 1100,
        }
        out = apply_adapter("historical_summary", data)
        # KPI strip — should have both RPS and PSR
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current RPS" in kpi_labels
        assert "Current PSR" in kpi_labels
        # Summary table — should mention RPS, PSR, and TTM revenue field
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "RPS" in rows_text
        assert "PSR" in rows_text
        # The TTM revenue should be in the current block (engine-specific field)
        # The adapter includes engine-specific fields (ttm_rev, pl, ttm_earnings, shares)


class TestHistoricalRoeChartAdapter:
    def test_roe_chart_single_dataset(self):
        """roe_chart should produce ONE dataset (fundamental ratio, no per-share)."""
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-03-31", "roe": 0.34},
                {"date": "2024-06-30", "roe": None},  # gap
                {"date": "2024-09-30", "roe": 0.38},
            ],
        }
        out = apply_adapter("historical_roe_chart", data)
        assert out["x"] == ["2024-03-31", "2024-06-30", "2024-09-30"]
        assert len(out["datasets"]) == 1  # single dataset (fundamental ratio)
        # Dataset 0 = ratio (ROE), NO yAxisID (single axis)
        assert out["datasets"][0]["label"] == "ROE"
        assert out["datasets"][0]["data"] == [0.34, None, 0.38]
        assert "yAxisID" not in out["datasets"][0]  # no dual-axis for fundamental

    def test_roe_chart_error_result(self):
        out = apply_adapter("historical_roe_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_roe_chart_empty_series(self):
        out = apply_adapter("historical_roe_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalSummaryRoeMetric:
    def test_summary_roe_metric(self):
        """Summary adapter with metric=roe should render ROE + TTM Earnings + PL (no per-share)."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "roe",
            "per_share_label": None,  # fundamental ratio -- no per-share
            "ratio_label": "ROE",
            "current": {
                "date": "2024-06-30", "roe": 0.34,
                "ttm_earnings": 120e9, "pl": 350e9,
            },
            "averages": {"1y": 0.32, "3y": 0.30, "5y": 0.28},
            "range": {"min": 0.15, "max": 0.40},
            "percentile": 75.0,
            "interpretation": "expensive (above 75th percentile of history)",
            "data_points": 20,
        }
        out = apply_adapter("historical_summary", data)
        # KPI strip -- should have ROE but NO per-share KPI
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current ROE" in kpi_labels
        assert "Current LPA" not in kpi_labels  # no per-share for fundamental
        assert "Current VPA" not in kpi_labels
        # Summary table -- should mention ROE, TTM Earnings, PL
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "ROE" in rows_text
        assert "TTM Earnings" in rows_text
        assert "Patrim" in rows_text  # Patrimônio Líquido


# ── Backtest adapter ────────────────────────────────────────────────────────

BACKTEST_RESULT = {
    "status": "ok",
    "ticker": "PETR4",
    "strategy": "value_pe",
    "strategy_description": "Buy when P/L < 5 (cheap valuation)",
    "start_date": "2022-01-01",
    "end_date": "2025-01-01",
    "initial_capital": 10000.0,
    "final_equity": 15800.50,
    "performance": {
        "total_return_pct": 58.01,
        "cagr_pct": 16.55,
        "max_drawdown_pct": 12.34,
        "sharpe_ratio": 1.42,
        "win_rate_pct": 60.0,
        "num_trades": 5,
        "buy_hold_return_pct": 35.20,
        "alpha_vs_buy_hold": 22.81,
    },
    "trades": [
        {"entry_date": "2022-03-15", "entry_price": 28.50,
         "exit_date": "2022-09-20", "exit_price": 34.20,
         "shares": 350, "pnl": 1995.00, "return_pct": 20.00,
         "holding_days": 130, "exit_reason": "max_holding"},
        {"entry_date": "2023-02-10", "entry_price": 26.00,
         "exit_date": "2023-08-15", "exit_price": 31.50,
         "shares": 400, "pnl": 2200.00, "return_pct": 21.15,
         "holding_days": 145, "exit_reason": "max_holding"},
    ],
    "equity_curve": [
        {"date": "2022-03-15", "equity": 10000.00},
        {"date": "2022-09-20", "equity": 11995.00},
        {"date": "2023-02-10", "equity": 11995.00},
        {"date": "2023-08-15", "equity": 14195.00},
    ],
}


class TestBacktestAdapter:
    def test_backtest_kpis_present(self):
        """Backtest adapter should emit 6 KPIs: CAGR, Return, DD, Sharpe, Win, Alpha."""
        out = apply_adapter("backtest", BACKTEST_RESULT)
        labels = [k["label"] for k in out["kpis"]]
        assert "CAGR" in labels
        assert "Total Return" in labels
        assert "Max Drawdown" in labels
        assert "Sharpe" in labels
        assert "Win Rate" in labels
        assert "Alpha" in labels
        # KPI values are pre-formatted strings
        cagr = next(k for k in out["kpis"] if k["label"] == "CAGR")
        assert cagr["value"] == "16.55%"

    def test_backtest_has_4_sections(self):
        """Sections: Strategy (text), Equity Curve (chart), Trade Log (table), Performance (table)."""
        out = apply_adapter("backtest", BACKTEST_RESULT)
        assert len(out["sections"]) == 4
        titles = [s["title"] for s in out["sections"]]
        assert "Strategy" in titles
        assert "Equity Curve" in titles
        assert "Trade Log" in titles
        assert "Performance Summary" in titles

    def test_backtest_strategy_section_is_text(self):
        out = apply_adapter("backtest", BACKTEST_RESULT)
        sec = next(s for s in out["sections"] if s["title"] == "Strategy")
        assert sec["type"] == "text"
        # Plain text — no HTML markup (autoescape would mangle it).
        # NOTE: the strategy description itself contains "P/L < 5", so the
        # presence of "<" alone is fine; we just check there are no HTML tags.
        assert "PETR4" in sec["text"]
        assert "value_pe" in sec["text"]
        for tag in ("<strong>", "<br", "<code>", "<div", "<p>", "<a "):
            assert tag not in sec["text"]

    def test_backtest_equity_section_is_chart_config(self):
        """Equity section should produce a Chart.js config dict (chart_data)."""
        out = apply_adapter("backtest", BACKTEST_RESULT)
        sec = next(s for s in out["sections"] if s["title"] == "Equity Curve")
        assert sec["type"] == "chart"
        cfg = sec["chart_data"]
        # Must be a full Chart.js config (type + data + options)
        assert cfg["type"] == "line"
        assert "datasets" in cfg["data"]
        assert cfg["data"]["datasets"][0]["label"] == "Equity (R$)"
        # Equity values landed oldest-first
        assert cfg["data"]["datasets"][0]["data"] == [10000.00, 11995.00, 11995.00, 14195.00]
        assert cfg["data"]["labels"] == ["2022-03-15", "2022-09-20", "2023-02-10", "2023-08-15"]

    def test_backtest_trade_log_table_shape(self):
        out = apply_adapter("backtest", BACKTEST_RESULT)
        sec = next(s for s in out["sections"] if s["title"] == "Trade Log")
        assert sec["type"] == "table"
        assert "Entry Date" in sec["columns"]
        assert "Exit Date" in sec["columns"]
        assert "PnL (R$)" in sec["columns"]
        assert "Return %" in sec["columns"]
        assert "Exit Reason" in sec["columns"]
        # Two trades from the synthetic result
        assert len(sec["rows"]) == 2
        # First trade values landed in column order
        first = sec["rows"][0]
        assert first[0] == "2022-03-15"   # entry_date
        assert first[1] == 28.50          # entry_price
        assert first[2] == "2022-09-20"   # exit_date
        assert first[3] == 34.20          # exit_price
        assert first[4] == 350            # shares
        assert first[5] == 1995.00        # pnl
        assert first[6] == 20.00          # return_pct
        assert first[7] == 130            # holding_days
        assert first[8] == "max_holding"  # exit_reason
        # Per-column format specs
        assert sec["formats"]["Entry Price"] == "brl_full"
        assert sec["formats"]["Return %"] == "pct_raw"
        assert sec["formats"]["Shares"] == "int"

    def test_backtest_performance_summary_shape(self):
        out = apply_adapter("backtest", BACKTEST_RESULT)
        sec = next(s for s in out["sections"] if s["title"] == "Performance Summary")
        assert sec["type"] == "table"
        assert sec["columns"] == ["Metric", "Value"]
        # Should include the headline metrics
        rows_text = " ".join(str(r) for r in sec["rows"])
        assert "CAGR" in rows_text
        assert "Sharpe" in rows_text
        assert "Alpha" in rows_text
        assert "Buy & Hold" in rows_text

    def test_backtest_company_is_ticker(self):
        out = apply_adapter("backtest", BACKTEST_RESULT)
        assert out["company"] == "PETR4"

    def test_backtest_error_renders_status_table(self):
        out = apply_adapter("backtest", {"status": "error", "error": "no price data"})
        assert out["sections"][0]["rows"][0] == ["error", "no price data"]

    def test_backtest_no_trades_still_renders(self):
        """A backtest with zero trades should still produce all 4 sections."""
        result = dict(BACKTEST_RESULT)
        result["trades"] = []
        out = apply_adapter("backtest", result)
        trade_sec = next(s for s in out["sections"] if s["title"] == "Trade Log")
        assert len(trade_sec["rows"]) == 0
        assert "0 trade" in trade_sec["note"]


# ── Synthetic backtest.dashboard() result ───────────────────────────────────
# Mirrors the shape produced by skills/cvm/backtest/modes/dashboard.py:
#   {"status": "ok", "ticker": ..., "strategy": ..., "tabs": [...], "kpis": [...]}
# Each KPI carries a `unit` field (pct/num/int/BRL/ratio/x) that the
# backtest_dashboard adapter maps to a format spec.

BACKTEST_DASHBOARD = {
    "status": "ok",
    "ticker": "PETR4",
    "strategy": "value_pe",
    "tabs": [
        {
            "name": "Overview",
            "sections": [
                {"title": "Strategy", "type": "text",
                 "text": "Ticker: PETR4    Strategy: value_pe\n"
                         "Description: Buy when P/L < 5 (cheap valuation)\n"
                         "Period: 2022-01-01 -> 2025-01-01\n"
                         "Capital: R$ 10,000.00 -> R$ 15,800.50"},
                {"title": "Equity Curve", "type": "chart",
                 "chart_data": {
                     "type": "line",
                     "data": {
                         "labels": ["2022-03-15", "2022-09-20",
                                    "2023-02-10", "2023-08-15"],
                         "datasets": [{
                             "label": "Equity (R$)",
                             "data": [10000.0, 11995.0, 11995.0, 14195.0],
                             "borderColor": "#0d9488",
                             "backgroundColor": "rgba(13, 148, 136, 0.15)",
                             "borderWidth": 2,
                             "tension": 0.3,
                             "fill": True,
                         }],
                     },
                     "options": {"responsive": True, "maintainAspectRatio": False},
                 },
                 },
            ],
        },
        {
            "name": "Trades",
            "sections": [
                {"title": "Trade Log", "type": "table",
                 "columns": ["Entry Date", "Entry Price", "Exit Date", "Exit Price",
                             "Shares", "PnL (R$)", "Return %", "Holding Days",
                             "Exit Reason"],
                 "rows": [
                     ["2022-03-15", 28.50, "2022-09-20", 34.20,
                      350, 1995.00, 20.00, 130, "max_holding"],
                     ["2023-02-10", 26.00, "2023-08-15", 31.50,
                      400, 2200.00, 21.15, 145, "max_holding"],
                 ],
                 "formats": {"Entry Price": "brl_full", "Exit Price": "brl_full",
                             "PnL (R$)": "brl_full", "Return %": "pct_raw",
                             "Shares": "int", "Holding Days": "int",
                             "Entry Date": "text", "Exit Date": "text",
                             "Exit Reason": "text"},
                 "note": "2 trade(s) executed."},
            ],
        },
        {
            "name": "Performance",
            "sections": [
                {"title": "Performance Summary", "type": "table",
                 "columns": ["Metric", "Value"],
                 "rows": [
                     ["Total Return", "58.01%"],
                     ["CAGR", "16.55%"],
                     ["Max Drawdown", "12.34%"],
                     ["Sharpe Ratio", "1.42"],
                     ["Win Rate", "60.0%"],
                     ["Number of Trades", "5"],
                     ["Buy & Hold Return", "35.20%"],
                     ["Alpha vs Buy & Hold", "22.81%"],
                 ]},
            ],
        },
    ],
    "kpis": [
        {"label": "CAGR",          "value": "16.55%", "unit": "pct"},
        {"label": "Total Return",  "value": "58.01%", "unit": "pct"},
        {"label": "Max Drawdown",  "value": "12.34%", "unit": "pct"},
        {"label": "Sharpe",        "value": "1.42",   "unit": "num"},
        {"label": "Win Rate",      "value": "60.0%",  "unit": "pct"},
        {"label": "Alpha",         "value": "22.81%", "unit": "pct"},
    ],
}


class TestBacktestDashboardAdapter:
    """Tests for the backtest_dashboard adapter (consumes backtest.dashboard())."""

    def test_returns_3_tabs(self):
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        assert out["company"] == "PETR4"
        assert len(out["tabs"]) == 3
        names = [t["name"] for t in out["tabs"]]
        assert names == ["Overview", "Trades", "Performance"]

    def test_top_level_kpis_present(self):
        """6 KPI cards at the top level with exact labels."""
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        assert len(out["kpis"]) == 6
        labels = [k["label"] for k in out["kpis"]]
        assert labels == ["CAGR", "Total Return", "Max Drawdown",
                          "Sharpe", "Win Rate", "Alpha"]

    def test_kpi_values_preformatted(self):
        """KPI values should be strings (pass-through since report.py already
        pre-formatted them via apply_fmt)."""
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        for kpi in out["kpis"]:
            assert isinstance(kpi["value"], str)
            assert kpi["value"]  # non-empty
        # pct KPIs end with %, num KPIs are plain numbers.
        cagr = next(k for k in out["kpis"] if k["label"] == "CAGR")
        assert cagr["value"].endswith("%")
        assert cagr["format"] == "pct_raw"
        sharpe = next(k for k in out["kpis"] if k["label"] == "Sharpe")
        assert sharpe["format"] == "num"

    def test_overview_tab_passes_through_sections(self):
        """Overview tab sections should pass through verbatim (Strategy text
        + Equity Curve chart)."""
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        overview = next(t for t in out["tabs"] if t["name"] == "Overview")
        titles = [s["title"] for s in overview["sections"]]
        assert titles == ["Strategy", "Equity Curve"]
        # Strategy section is text.
        strategy_sec = overview["sections"][0]
        assert strategy_sec["type"] == "text"
        assert "PETR4" in strategy_sec["text"]
        # Equity curve section is a chart with Chart.js config.
        equity_sec = overview["sections"][1]
        assert equity_sec["type"] == "chart"
        cfg = equity_sec["chart_data"]
        assert cfg["type"] == "line"
        assert cfg["data"]["datasets"][0]["label"] == "Equity (R$)"

    def test_trades_tab_passes_through_table(self):
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        trades_tab = next(t for t in out["tabs"] if t["name"] == "Trades")
        assert len(trades_tab["sections"]) == 1
        sec = trades_tab["sections"][0]
        assert sec["type"] == "table"
        assert sec["title"] == "Trade Log"
        # Two synthetic trades.
        assert len(sec["rows"]) == 2
        # Column format specs preserved.
        assert sec["formats"]["Entry Price"] == "brl_full"
        assert sec["formats"]["Return %"] == "pct_raw"

    def test_performance_tab_passes_through_table(self):
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        perf_tab = next(t for t in out["tabs"] if t["name"] == "Performance")
        assert len(perf_tab["sections"]) == 1
        sec = perf_tab["sections"][0]
        assert sec["type"] == "table"
        assert sec["title"] == "Performance Summary"
        # 8 metric rows.
        assert len(sec["rows"]) == 8
        rows_text = " ".join(str(r[0]) for r in sec["rows"])
        assert "CAGR" in rows_text
        assert "Sharpe Ratio" in rows_text
        assert "Alpha vs Buy & Hold" in rows_text

    def test_error_renders_status_table(self):
        out = apply_adapter("backtest_dashboard",
                            {"status": "error", "error": "no price data"})
        assert out["sections"][0]["title"] == "Backtest Dashboard"
        assert out["sections"][0]["rows"][0] == ["error", "no price data"]

    def test_missing_tabs_renders_error(self):
        """If the result has no tabs (run() failed before composing tabs),
        the adapter should error gracefully."""
        out = apply_adapter("backtest_dashboard",
                            {"status": "ok", "ticker": "PETR4"})
        assert "sections" in out
        assert out["sections"][0]["title"] == "Backtest Dashboard"

    def test_company_uses_ticker(self):
        """Adapter maps result['ticker'] -> out['company'] for the report tool."""
        out = apply_adapter("backtest_dashboard", BACKTEST_DASHBOARD)
        assert out["company"] == "PETR4"


# ── Synthetic comparison.dashboard() result ─────────────────────────────────
# Mirrors the shape produced by skills/cvm/comparison/modes/dashboard.py:
#   {"status": "ok", "tickers": [...], "tabs": [...], "kpis": [...]}
# 5 tabs: Overview (Compared Tickers + Per-Ticker Errors) / Valuation /
# Financials / Dividends / Growth.
# 4 top-level KPI cards (Cheapest P/L, Best ROE, Best Div Yield, Cheapest
# EV/EBITDA) with values pre-formatted by report.py as "<ticker> (<fmt>)".

COMPARISON_DASHBOARD = {
    "status": "ok",
    "tickers": ["PETR4", "VALE3"],
    "tabs": [
        {
            "name": "Overview",
            "sections": [
                {"title": "Compared Tickers", "type": "table",
                 "columns": ["Ticker", "Setor"],
                 "rows": [["PETR4", "Petróleo"], ["VALE3", "Mineração"]],
                 "formats": {"Ticker": "text", "Setor": "text"}},
                {"title": "Per-Ticker Errors (best-effort)", "type": "table",
                 "columns": ["#", "Error"],
                 "rows": [[1, "VALE3: valuation: no price"]],
                 "formats": {"#": "int", "Error": "text"}},
            ],
        },
        {
            "name": "Valuation",
            "sections": [
                {"title": "Valuation Ratios", "type": "table",
                 "columns": ["Ticker", "P/L", "EV/EBITDA", "Div Yield"],
                 "rows": [["PETR4", 8.2, 4.5, 0.12], ["VALE3", 6.5, 3.8, 0.09]],
                 "formats": {"Ticker": "text", "P/L": "num",
                             "EV/EBITDA": "num", "Div Yield": "pct"}},
            ],
        },
        {
            "name": "Financials",
            "sections": [
                {"title": "Financial Metrics (latest annual)", "type": "table",
                 "columns": ["Ticker", "Receita Líquida", "ROE"],
                 "rows": [["PETR4", 400_000_000_000, 0.15],
                          ["VALE3", 300_000_000_000, 0.14]],
                 "formats": {"Ticker": "text",
                             "Receita Líquida": "brl", "ROE": "pct"}},
            ],
        },
        {
            "name": "Dividends",
            "sections": [
                {"title": "Dividend Metrics", "type": "table",
                 "columns": ["Ticker", "Eventos (B3)"],
                 "rows": [["PETR4", 3], ["VALE3", 2]],
                 "formats": {"Ticker": "text", "Eventos (B3)": "int"}},
            ],
        },
        {
            "name": "Growth",
            "sections": [
                {"title": "Growth Metrics (QoQ + YoY + TTM)", "type": "table",
                 "columns": ["Ticker", "Receita QoQ", "Receita YoY"],
                 "rows": [["PETR4", 0.077, 0.40], ["VALE3", 0.05, 0.30]],
                 "formats": {"Ticker": "text",
                             "Receita QoQ": "pct_raw", "Receita YoY": "pct_raw"}},
            ],
        },
    ],
    "kpis": [
        {"label": "Cheapest P/L",       "value": "VALE3 (6,50)",  "unit": "num"},
        {"label": "Best ROE",           "value": "PETR4 (15,00%)","unit": "pct"},
        {"label": "Best Div Yield",     "value": "PETR4 (12,00%)","unit": "pct"},
        {"label": "Cheapest EV/EBITDA", "value": "VALE3 (3,80)",  "unit": "num"},
    ],
}


class TestComparisonDashboardAdapter:
    """Tests for the comparison_dashboard adapter (consumes comparison.dashboard())."""

    def test_returns_5_tabs(self):
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        assert out["company"] == "PETR4 vs VALE3"
        assert len(out["tabs"]) == 5
        names = [t["name"] for t in out["tabs"]]
        assert names == ["Overview", "Valuation", "Financials", "Dividends", "Growth"]

    def test_top_level_kpis_present(self):
        """4 KPI cards at the top level with exact labels."""
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        assert len(out["kpis"]) == 4
        labels = [k["label"] for k in out["kpis"]]
        assert labels == [
            "Cheapest P/L", "Best ROE", "Best Div Yield", "Cheapest EV/EBITDA",
        ]

    def test_kpi_values_preformatted(self):
        """KPI values pass through verbatim (report.py already pre-formatted
        them as '<ticker> (<fmt>)')."""
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        for kpi in out["kpis"]:
            assert isinstance(kpi["value"], str)
            assert kpi["value"]  # non-empty
        # num KPIs end with a number, pct KPIs end with %.
        cheapest_pl = next(k for k in out["kpis"] if k["label"] == "Cheapest P/L")
        assert cheapest_pl["value"].startswith("VALE3")
        assert cheapest_pl["format"] == "num"
        best_roe = next(k for k in out["kpis"] if k["label"] == "Best ROE")
        assert best_roe["value"].startswith("PETR4")
        assert best_roe["format"] == "pct"

    def test_overview_tab_passes_through_sections(self):
        """Overview tab sections pass through verbatim (Compared Tickers table
        + Per-Ticker Errors table)."""
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        overview = next(t for t in out["tabs"] if t["name"] == "Overview")
        titles = [s["title"] for s in overview["sections"]]
        assert titles == ["Compared Tickers", "Per-Ticker Errors (best-effort)"]
        tickers_sec = overview["sections"][0]
        assert tickers_sec["type"] == "table"
        assert tickers_sec["columns"] == ["Ticker", "Setor"]
        assert len(tickers_sec["rows"]) == 2

    def test_valuation_tab_passes_through_table(self):
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        valuation_tab = next(t for t in out["tabs"] if t["name"] == "Valuation")
        sec = valuation_tab["sections"][0]
        assert sec["type"] == "table"
        assert "P/L" in sec["columns"]
        assert "EV/EBITDA" in sec["columns"]
        # Format specs preserved.
        assert sec["formats"]["P/L"] == "num"

    def test_growth_tab_passes_through_table(self):
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        growth_tab = next(t for t in out["tabs"] if t["name"] == "Growth")
        sec = growth_tab["sections"][0]
        assert sec["type"] == "table"
        assert "Receita QoQ" in sec["columns"]
        assert sec["formats"]["Receita QoQ"] == "pct_raw"

    def test_error_renders_status_table(self):
        out = apply_adapter("comparison_dashboard",
                            {"status": "error", "error": "tickers required"})
        assert out["sections"][0]["title"] == "Comparison Dashboard"
        assert out["sections"][0]["rows"][0] == ["error", "tickers required"]

    def test_missing_tabs_renders_error(self):
        """If the result has no tabs (side_by_side failed before composing
        tabs), the adapter should error gracefully."""
        out = apply_adapter("comparison_dashboard",
                            {"status": "ok", "tickers": ["PETR4", "VALE3"]})
        assert "sections" in out
        assert out["sections"][0]["title"] == "Comparison Dashboard"

    def test_company_uses_tickers_joined(self):
        """Adapter joins tickers with ' vs ' for the report tool's company field."""
        out = apply_adapter("comparison_dashboard", COMPARISON_DASHBOARD)
        assert out["company"] == "PETR4 vs VALE3"


# ── Synthetic financials.dashboard() result ─────────────────────────────────

FINANCIALS_DASHBOARD = {
    "status": "ok",
    "company": "PETR4",
    "tabs": [
        {
            "name": "Overview",
            "kpis": [
                {"label": "Receita Líquida", "value": 500_000_000_000, "unit": "BRL"},
                {"label": "EBITDA", "value": 230_000_000_000, "unit": "BRL"},
                {"label": "Lucro Líquido", "value": 120_000_000_000, "unit": "BRL"},
                {"label": "Margem EBITDA", "value": 0.46, "unit": "ratio"},
                {"label": "ROE", "value": 0.30, "unit": "ratio"},
                {"label": "Dívida Líquida/EBITDA", "value": 0.82, "unit": "x"},
            ],
            "sections": [
                {"name": "kpis", "cards": []},
                {"name": "latest_annual", "period": "2023"},
                {"name": "latest_quarterly", "period": "4T23"},
                {"name": "freshness", "data": {
                    "dfp": {"last_updated": "2024-01-15"},
                    "itr": {"last_updated": "2024-01-15"},
                }},
            ],
        },
        {
            "name": "DRE",
            "sections": [
                {"name": "latest_annual", "metrics": {
                    "receita_liquida": 500_000_000_000,
                    "lucro_bruto": 200_000_000_000,
                    "ebit": 200_000_000_000,
                    "ebitda": 230_000_000_000,
                    "ebitda_method": "ebit+da",
                    "resultado_financeiro": -10_000_000_000,
                    "lucro_liquido": 120_000_000_000,
                    "da": 30_000_000_000,
                }, "ratios": {
                    "marg_bruta": 0.40,
                    "marg_ebit": 0.40,
                    "marg_ebitda": 0.46,
                    "marg_liquida": 0.24,
                }},
                {"name": "quarterly_trend", "periods": [
                    {"period": "1T24", "receita": 100e9, "ebitda": 50e9, "lucro_liquido": 25e9},
                    {"period": "4T23", "receita": 130e9, "ebitda": 60e9, "lucro_liquido": 30e9},
                ]},
            ],
        },
        {
            "name": "Balanço",
            "sections": [
                {"name": "latest_annual", "ativo": {
                    "ativo_total": 800_000_000_000,
                    "caixa": 34_000_000_000,
                }, "passivo": {
                    "patrimonio_liquido": 400_000_000_000,
                    "divida_bruta": 371_000_000_000,
                    "divida_liquida": 337_000_000_000,
                }},
            ],
        },
        {
            "name": "DFC",
            "sections": [
                {"name": "latest_annual", "metrics": {
                    "fco": 180_000_000_000,
                    "fci": -80_000_000_000,
                    "fcf": 100_000_000_000,
                }},
                {"name": "quarterly_trend", "periods": [
                    {"period": "1T24", "fco": 40e9, "fci": -20e9, "fcf": 20e9},
                    {"period": "4T23", "fco": 50e9, "fci": -25e9, "fcf": 25e9},
                ]},
            ],
        },
        {
            "name": "Ratios",
            "sections": [
                {"name": "ratio_grid", "date": "2024-01-15", "categories": {
                    "profitability": {"roe": 0.30, "roa": 0.15, "roic": 0.18,
                                       "gross_margin": 0.40, "net_margin": 0.24},
                    "liquidity": {"current_ratio": 1.5, "quick_ratio": 1.1,
                                  "cash_ratio": 0.30, "working_capital": 50e9},
                    "leverage": {"debt_equity": 0.93, "net_debt_ebitda": 0.82,
                                 "interest_coverage": 8.0, "cash_flow_to_debt": 0.80},
                }},
            ],
        },
    ],
}


class TestFinancialsDashboardAdapter:
    """[v1.5] Tests for the financials_dashboard adapter."""

    def test_returns_5_tabs(self):
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        assert out["company"] == "PETR4"
        assert len(out["tabs"]) == 5
        names = [t["name"] for t in out["tabs"]]
        assert names == ["Overview", "DRE", "Balanço", "DFC", "Ratios"]

    def test_overview_kpis_pulled_to_top_level(self):
        """The Overview tab's KPIs should be promoted to the top-level `kpis` field."""
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        assert len(out["kpis"]) == 6
        labels = [k["label"] for k in out["kpis"]]
        assert "Receita Líquida" in labels
        assert "ROE" in labels

    def test_overview_kpis_formatted_by_unit(self):
        """KPI values should be pre-formatted strings based on their `unit`."""
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        receita = next(k for k in out["kpis"] if k["label"] == "Receita Líquida")
        # BRL -> compact format R$ X,XX B
        assert "R$" in receita["value"]
        assert receita["format"] == "brl"
        roe = next(k for k in out["kpis"] if k["label"] == "ROE")
        # ratio -> pct format XX,XX%
        assert roe["value"].endswith("%")
        assert roe["format"] == "pct"

    def test_dre_tab_has_dre_table_and_trend(self):
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        dre_tab = next(t for t in out["tabs"] if t["name"] == "DRE")
        titles = [s.get("title", "") for s in dre_tab["sections"]]
        assert any("DRE" in t for t in titles)
        assert any("Trend" in t for t in titles)

    def test_balanco_tab_has_ativo_and_passivo(self):
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        balanco_tab = next(t for t in out["tabs"] if t["name"] == "Balanço")
        titles = [s.get("title", "") for s in balanco_tab["sections"]]
        assert any("Ativo" in t for t in titles)
        assert any("Passivo" in t for t in titles)

    def test_ratios_tab_is_ratio_grid_section(self):
        """The Ratios tab should produce a section with type=ratio_grid."""
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        ratios_tab = next(t for t in out["tabs"] if t["name"] == "Ratios")
        assert len(ratios_tab["sections"]) == 1
        sec = ratios_tab["sections"][0]
        assert sec["type"] == "ratio_grid"
        # categories should be a list of {label, items}
        assert isinstance(sec["categories"], list)
        cat_labels = [c["label"] for c in sec["categories"]]
        assert "Rentabilidade" in cat_labels  # profitability -> PT-BR
        assert "Liquidez" in cat_labels        # liquidity
        assert "Endividamento" in cat_labels   # leverage

    def test_ratio_grid_items_have_label_and_value(self):
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        ratios_tab = next(t for t in out["tabs"] if t["name"] == "Ratios")
        sec = ratios_tab["sections"][0]
        profitability = next(c for c in sec["categories"] if c["label"] == "Rentabilidade")
        assert len(profitability["items"]) > 0
        first_item = profitability["items"][0]
        assert "label" in first_item
        assert "value" in first_item
        # ROE value should be pct-formatted
        roe_item = next(i for i in profitability["items"] if i["label"] == "ROE")
        assert roe_item["value"].endswith("%")

    def test_error_renders_status_table(self):
        out = apply_adapter("financials_dashboard",
                            {"status": "not_found", "error": "company not found"})
        assert out["sections"][0]["title"] == "Financials Dashboard"

    def test_freshness_section_converted_to_table(self):
        """The Overview tab's freshness section should become a small table."""
        out = apply_adapter("financials_dashboard", FINANCIALS_DASHBOARD)
        overview_tab = next(t for t in out["tabs"] if t["name"] == "Overview")
        titles = [s.get("title", "") for s in overview_tab["sections"]]
        assert "Data Freshness" in titles
        freshness_sec = next(s for s in overview_tab["sections"]
                             if s.get("title") == "Data Freshness")
        assert freshness_sec["type"] == "table"
        assert "Database" in freshness_sec["columns"]
        assert "Last Updated" in freshness_sec["columns"]


# ── Synthetic valuation.ratios() result ─────────────────────────────────────

VALUATION_DASHBOARD_INPUT = {
    "status": "ok",
    "ticker": "PETR4",
    "ratios": {
        "price": 38.5, "price_date": "2024-01-15", "price_source": "investsite",
        "total_shares": 13e9, "market_cap": 500.5e9,
        "ev": 570.5e9, "ebitda": 85e9, "ebitda_method": "ebit+da",
        "lucro_liquido": 120e9, "receita_liquida": 280e9,
        "patrimonio_liquido": 350e9, "divida_bruta": 100e9, "caixa": 30e9,
        "p_l": 4.17, "p_vpa": 1.43, "p_ebit": 7.15, "p_fco": 6.26, "p_fcf": 10.01,
        "psr": 1.79, "ev_ebitda": 6.71, "ev_sales": 2.05, "ev_fcf": 11.41,
        "dividend_yield": 0.048, "dpa": 0.048,
        "divida_liquida_ebitda": 0.82,
        # From compute_all_ratios():
        "roe": 0.28, "roa": 0.15, "roic": 0.18,
        "gross_margin": 0.35, "operating_margin": 0.25, "net_margin": 0.20,
        "ebitda_margin": 0.30, "ocf_margin": 0.286, "fcf_margin": 0.179,
        "cash_ratio": 0.30, "current_ratio": 1.5, "quick_ratio": 1.10,
        "working_capital": 50e9,
        "debt_equity": 0.29, "net_debt_ebitda": 0.82,
        "interest_coverage": 8.0, "cash_flow_to_debt": 0.80,
        "asset_turnover": 0.35, "inventory_turnover": 5.0,
        "receivables_turnover": 8.0, "fixed_asset_turnover": 0.80,
        "capex_revenue": 0.05,
        "retention_ratio": 0.50, "sustainable_growth": 0.14,
        "graham_number": 75.0, "price_to_tangible_book": 1.55,
        "effective_tax_rate": 0.34,
    },
    "sources": {},
}


class TestValuationDashboardAdapter:
    """[v1.5] Tests for the valuation_dashboard adapter."""

    def test_returns_5_tabs(self):
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        assert out["company"] == "PETR4"
        assert len(out["tabs"]) == 5
        names = [t["name"] for t in out["tabs"]]
        assert names == ["Overview", "Multiples", "Profitability",
                         "Liquidity & Leverage", "Efficiency & Growth"]

    def test_overview_kpis_present(self):
        """Top-level KPIs: P/L, P/VPA, EV/EBITDA, Div Yield, Market Cap, ROE."""
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        assert len(out["kpis"]) == 6
        labels = [k["label"] for k in out["kpis"]]
        assert "P/L" in labels
        assert "P/VPA" in labels
        assert "EV/EBITDA" in labels
        assert "Div Yield" in labels
        assert "Market Cap" in labels
        assert "ROE" in labels

    def test_overview_kpis_preformatted(self):
        """KPI values are pre-formatted strings (apply_fmt applied)."""
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        pl = next(k for k in out["kpis"] if k["label"] == "P/L")
        # num spec -> "4,17" (BR separator)
        assert "," in pl["value"]
        # Market Cap -> brl compact -> contains "R$"
        mcap = next(k for k in out["kpis"] if k["label"] == "Market Cap")
        assert "R$" in mcap["value"]
        # Div Yield -> pct -> ends with %
        dy = next(k for k in out["kpis"] if k["label"] == "Div Yield")
        assert dy["value"].endswith("%")

    def test_overview_tab_has_key_value_table(self):
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        overview_tab = next(t for t in out["tabs"] if t["name"] == "Overview")
        assert len(overview_tab["sections"]) >= 1
        sec = overview_tab["sections"][0]
        assert sec["type"] == "table"
        assert sec["columns"] == ["Indicador", "Valor"]
        # Should include headline metrics
        all_rows_text = " ".join(str(r) for r in sec["rows"])
        assert "Market Cap" in all_rows_text
        assert "P/L" in all_rows_text

    def test_multiples_tab_has_all_9_multiples(self):
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        multiples_tab = next(t for t in out["tabs"] if t["name"] == "Multiples")
        sec = multiples_tab["sections"][0]
        labels_in_table = [r[0] for r in sec["rows"]]
        for expected in ("P/L", "P/VPA", "P/EBIT", "P/FCO", "P/FCF",
                         "PSR", "EV/EBITDA", "EV/Sales", "EV/FCF"):
            assert expected in labels_in_table, f"Missing multiple: {expected}"

    def test_profitability_tab_has_roe_roa_roic_margins(self):
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        profitability_tab = next(t for t in out["tabs"] if t["name"] == "Profitability")
        sec = profitability_tab["sections"][0]
        labels_in_table = [r[0] for r in sec["rows"]]
        for expected in ("ROE", "ROA", "ROIC", "Marg. Bruta",
                         "Marg. Líquida", "Marg. EBITDA"):
            assert expected in labels_in_table, f"Missing profitability metric: {expected}"

    def test_liquidity_leverage_tab_has_all_metrics(self):
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        ll_tab = next(t for t in out["tabs"] if t["name"] == "Liquidity & Leverage")
        sec = ll_tab["sections"][0]
        labels_in_table = [r[0] for r in sec["rows"]]
        for expected in ("Liquidez Corrente", "Liquidez Seca", "Liquidez Imediata",
                         "Dívida/PL", "Dív. Líq/EBITDA", "Cobertura Juros"):
            assert expected in labels_in_table, f"Missing liquidity/leverage metric: {expected}"

    def test_efficiency_growth_tab_has_all_metrics(self):
        out = apply_adapter("valuation_dashboard", VALUATION_DASHBOARD_INPUT)
        eg_tab = next(t for t in out["tabs"] if t["name"] == "Efficiency & Growth")
        sec = eg_tab["sections"][0]
        labels_in_table = [r[0] for r in sec["rows"]]
        for expected in ("Giro do Ativo", "Giro Estoque",
                         "Taxa de Retenção", "Crescimento Sustentável",
                         "Taxa de Tributo Efetiva"):
            assert expected in labels_in_table, f"Missing efficiency/growth metric: {expected}"

    def test_summary_input_adds_availability_section(self):
        """If the input has data_availability (summary() was called), the
        Overview tab should include a Data Source Availability section."""
        result = dict(VALUATION_DASHBOARD_INPUT)
        result["data_availability"] = {
            "price": "ok", "dfp_ttm": "ok", "fre_shares": "ok",
        }
        out = apply_adapter("valuation_dashboard", result)
        overview_tab = next(t for t in out["tabs"] if t["name"] == "Overview")
        titles = [s.get("title", "") for s in overview_tab["sections"]]
        assert "Data Source Availability" in titles

    def test_error_renders_status_table(self):
        out = apply_adapter("valuation_dashboard",
                            {"status": "error", "error": "price unavailable"})
        assert out["sections"][0]["title"] == "Valuation Dashboard"

    def test_missing_ratios_renders_error(self):
        """If the result has no ratios dict, the adapter should error gracefully."""
        out = apply_adapter("valuation_dashboard",
                            {"status": "ok", "ticker": "PETR4"})
        # Falls through to _error_table (no ratios to render)
        assert "sections" in out
        assert out["sections"][0]["title"] == "Valuation Dashboard"

