"""Shared fixtures for the comparison skill tests.

[Phase 4] Extracted from the original single-file `test_comparison.py` so
each mode (validation / side_by_side / summary / growth / route) can live
in its own per-mode test module. The fixture provides:

  - Synthetic skill results (VAL_*, FIN_*, DIV_*) that mirror the real
    shapes returned by valuation.ratios(), financials.summary(), and
    dividends.summary() — including the [v1.3] additions in valuation
    (roe, roa, margem_liquida, divida_pl, liquidez_corrente from
    calculations metrics).
  - A `mock_skills` fixture that monkeypatches the 3 underlying skills to
    return the synthetic data.

Env vars (PLANNER_MODEL etc.) are set by the parent conftest at
``tests/skills/cvm/conftest.py``.
"""
from __future__ import annotations

import pytest

# ── Synthetic skill results (mirror the real skill output shapes) ────────────

VAL_PETR4 = {
    "status": "ok", "ticker": "PETR4",
    "ratios": {"price": 38.5, "p_l": 8.2, "p_vpa": 1.9, "ev_ebitda": 4.5,
               "dividend_yield": 0.12, "market_cap": 500_000_000_000,
               "total_shares": 13_000_000_000, "eps": 4.7, "vpa": 20.1,
               "ev": 510_000_000_000, "psr": 1.2, "p_ebit": 6.1, "dpa": 2.5,
               # [v1.3] New metrics from calculations via valuation.ratios()
               "roe": 0.25, "roa": 0.06, "margem_liquida": 0.15,
               "divida_pl": 0.50, "liquidez_corrente": 1.8},
    "sources": {},
}

VAL_VALE3 = {
    "status": "ok", "ticker": "VALE3",
    "ratios": {"price": 60.0, "p_l": 6.5, "p_vpa": 1.5, "ev_ebitda": 3.8,
               "dividend_yield": 0.09, "market_cap": 300_000_000_000,
               "total_shares": 5_000_000_000, "eps": 9.2, "vpa": 40.0,
               "ev": 320_000_000_000, "psr": 2.1, "p_ebit": 5.0, "dpa": 3.1,
               # [v1.3] New metrics from calculations via valuation.ratios()
               "roe": 0.18, "roa": 0.07, "margem_liquida": 0.17,
               "divida_pl": 0.43, "liquidez_corrente": 2.1},
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

# ── Growth mode synthetic quarterly data ─────────────────────────────────────

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


def _mock_skills(monkeypatch, val_map, fin_map, div_map):
    """Monkeypatch the 3 underlying skills to return synthetic data.

    Each map is keyed by uppercase ticker. Tickers not in the map return a
    status=error response so the best-effort path can be tested.
    """
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


@pytest.fixture
def mock_skills():
    """Return the `_mock_skills` helper so per-mode tests can call it.

    Usage:
        def test_x(mock_skills, monkeypatch):
            mock_skills(monkeypatch,
                        {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                        {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                        {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
            ...
    """
    return _mock_skills


@pytest.fixture
def petr_vale_env(mock_skills, monkeypatch):
    """Pre-built 2-ticker environment (PETR4 + VALE3) with all 3 skills mocked.

    Convenience: most side_by_side / summary / route tests want exactly this
    setup. Tests that need a different combination (e.g. one ticker failing)
    can call `mock_skills` directly instead.
    """
    mock_skills(monkeypatch,
                {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
    return {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3}
