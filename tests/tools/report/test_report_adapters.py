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
        assert len(names) == 28

    def test_expected_adapter_names(self):
        expected = {
            "financials_quarterly", "financials_annual", "financials_summary",
            "financials_quarterly_chart",
            "valuation_ratios", "valuation_summary",
            "shareholders_shareholders", "shareholders_free_float",
            "shareholders_equity_structure", "shareholders_summary",
            "dividends_history", "dividends_annual", "dividends_summary",
            "comparison_side_by_side", "comparison_summary", "comparison_growth",
            "cotahist_close_chart",
            "cotahist_candlestick_chart",
            "screener_sector",
            "insider_history", "insider_by_role", "insider_summary",
            "governance_practices", "governance_score", "governance_by_chapter",
            "historical_pe_chart", "historical_vpa_chart", "historical_summary",
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

class TestHistoricalPeChartAdapter:
    def test_pe_chart_from_result(self):
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-01-15", "pe": 4.5},
                {"date": "2024-02-15", "pe": None},  # gap
                {"date": "2024-03-15", "pe": 5.2},
            ],
        }
        out = apply_adapter("historical_pe_chart", data)
        assert out["x"] == ["2024-01-15", "2024-02-15", "2024-03-15"]
        assert out["datasets"][0]["label"] == "P/L"
        assert out["datasets"][0]["data"] == [4.5, None, 5.2]

    def test_pe_chart_error_result(self):
        out = apply_adapter("historical_pe_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_pe_chart_empty_series(self):
        out = apply_adapter("historical_pe_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalVpaChartAdapter:
    def test_vpa_chart_from_result(self):
        data = {
            "status": "ok",
            "series": [
                {"date": "2024-01-15", "vpa": 1.45},
                {"date": "2024-02-15", "vpa": None},  # gap
                {"date": "2024-03-15", "vpa": 1.52},
            ],
        }
        out = apply_adapter("historical_vpa_chart", data)
        assert out["x"] == ["2024-01-15", "2024-02-15", "2024-03-15"]
        assert out["datasets"][0]["label"] == "P/VPA"
        assert out["datasets"][0]["data"] == [1.45, None, 1.52]

    def test_vpa_chart_error_result(self):
        out = apply_adapter("historical_vpa_chart",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table

    def test_vpa_chart_empty_series(self):
        out = apply_adapter("historical_vpa_chart",
                            {"status": "ok", "series": []})
        assert "sections" in out  # error table


class TestHistoricalSummaryAdapter:
    def test_summary_pe_metric(self):
        """Summary adapter with metric=pe should render P/L rows."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "pe",
            "current": {
                "date": "2024-07-26", "pe": 4.75, "price": 38.5,
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
        # KPI strip
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current P/L" in kpi_labels
        assert "Percentile" in kpi_labels
        # Summary table — should mention P/L and TTM Earnings (pe-specific)
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "P/L" in rows_text
        assert "TTM Earnings" in rows_text

    def test_summary_vpa_metric(self):
        """Summary adapter with metric=vpa should render P/VPA + PL rows."""
        data = {
            "status": "ok",
            "company": "PETR4",
            "metric": "vpa",
            "current": {
                "date": "2024-07-26", "vpa": 1.45, "price": 38.5,
                "pl": 350e9, "shares": 13e9,
            },
            "averages": {"1y": 1.5, "3y": 1.6, "5y": 1.7},
            "range": {"min": 0.9, "max": 2.1},
            "percentile": 30.0,
            "interpretation": "fair (between 25th-75th percentile of history)",
            "data_points": 1100,
        }
        out = apply_adapter("historical_summary", data)
        # KPI strip — should say "Current P/VPA" not "Current P/L"
        kpi_labels = [k["label"] for k in out["kpis"]]
        assert "Current P/VPA" in kpi_labels
        # Summary table — should mention P/VPA and Patrimônio Líquido (vpa-specific)
        rows_text = " ".join(str(r) for r in out["sections"][0]["rows"])
        assert "P/VPA" in rows_text
        assert "Patrim" in rows_text  # "Patrimônio Líquido"
        # Should NOT have TTM Earnings row for vpa metric
        assert "TTM Earnings" not in rows_text

    def test_summary_error_result(self):
        out = apply_adapter("historical_summary",
                            {"status": "not_found", "error": "no data"})
        assert "sections" in out  # error table
