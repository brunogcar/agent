"""skills/cvm/comparison/helpers.py -- Column definitions + growth math.

Shared constants + pure-Python helpers used by side_by_side / summary /
growth / dashboard modes. No DB access, no skill calls -- just data
shaping + simple arithmetic.

Two groups:
  1. Column definition lists (_VALUATION_COLS, _FINANCIALS_COLS,
     _DIVIDENDS_COLS, _SUMMARY_COLS, _GROWTH_COLS). Each is a list of
     (column_label, dict_key, spec) tuples consumed by
     ``fetchers._build_section()``.
  2. Growth math (_compute_growth, _pct_change). The dashboard + growth
     modes call _compute_growth() to derive QoQ + YoY change from a
     financials.quarterly() result. _pct_change() is the underlying
     sign-change-guarded ratio helper.
"""
from __future__ import annotations


# ── Valuation columns (from valuation.ratios) ────────────────────────────────
# Each is (column_name, ratios_key, spec). Multiples use "num", BRL uses "brl",
# fractions use "pct".
# [v1.3] Added ROE, ROA, Marg. Líquida, Dívida/PL, Liquidez Corrente — these
# are returned directly by valuation.ratios() since Phase 2B (calculations
# metrics roe_at, roa_at, net_margin_at, debt_equity_at, current_ratio_at are
# composed inside valuation.ratios and exposed in the ratios dict). The same
# metrics also appear in the financials section (computed by compute_ratios
# from the raw statement dict); the valuation column shows the calculations
# engine value (point-in-time TTM snapshot), the financials column shows the
# annual statement value. Both are useful — they cross-check each other.
_VALUATION_COLS = [
    ("Preço",            "price",            "brl_full"),
    ("Market Cap",       "market_cap",       "brl"),
    ("EV",               "ev",               "brl"),
    ("P/L",              "p_l",              "num"),
    ("P/VPA",            "p_vpa",            "num"),
    ("P/EBIT",           "p_ebit",           "num"),
    ("EV/EBITDA",        "ev_ebitda",        "num"),
    ("PSR",              "psr",              "num"),
    ("Div Yield",        "dividend_yield",   "pct"),
    ("DPA",              "dpa",              "brl_full"),
    ("EPS",              "eps",              "brl_full"),
    ("VPA",              "vpa",              "brl_full"),
    ("Total Ações",      "total_shares",     "int"),
    # [v1.3] New — calculations metrics surfaced via valuation.ratios()
    ("ROE (val)",        "roe",              "pct"),
    ("ROA (val)",        "roa",              "pct"),
    ("Marg. Líq. (val)", "margem_liquida",   "pct"),
    ("Dívida/PL",        "divida_pl",        "num"),
    ("Liquidez Corrente","liquidez_corrente","num"),
    # [v1.4] New — v1.3 calculations metrics surfaced via valuation.ratios()
    ("EV/Receita",       "ev_sales",         "num"),
    ("EV/FCF",           "ev_fcf",           "num"),
    ("Liquidez Seca",    "quick_ratio",      "num"),
    ("Índice Caixa",     "cash_ratio",       "num"),
    ("Marg. FCO",        "ocf_margin",       "pct"),
    ("Marg. FCF",        "fcf_margin",       "pct"),
    ("Cap. Giro",        "working_capital",  "brl"),
    ("FCO/Dívida",       "cash_flow_to_debt","num"),
    ("Taxa Retenção",    "retention_ratio",  "pct"),
    ("Cresc. Sust.",     "sustainable_growth","pct"),
    ("Cobertura Juros",  "interest_coverage","num"),
    ("Giro Estoque",     "inventory_turnover","num"),
    ("Giro Receber",     "receivables_turnover","num"),
    ("Giro Imob.",       "fixed_asset_turnover","num"),
    ("P/VPA Tang.",      "p_tangible_book",  "num"),
]

# ── Financials columns (from financials.summary -> latest_annual) ────────────
_FINANCIALS_COLS = [
    ("Receita Líquida",  "receita_liquida",      "brl"),
    ("Lucro Bruto",      "lucro_bruto",          "brl"),
    ("EBIT",             "ebit",                 "brl"),
    ("EBITDA",           "ebitda",               "brl"),
    ("Lucro Líquido",    "lucro_liquido",        "brl"),
    ("Ativo Total",      "ativo_total",          "brl"),
    ("Patrimônio Líq.",  "patrimonio_liquido",   "brl"),
    ("Caixa",            "caixa",                "brl"),
    ("Dívida Bruta",     "divida_bruta",         "brl"),
    ("FCO",              "fco",                  "brl"),
    ("Marg. Bruta",      "marg_bruta",           "pct"),
    ("Marg. EBITDA",     "marg_ebitda",          "pct"),
    ("Marg. Líquida",    "marg_liquida",         "pct"),
    ("ROE",              "roe",                  "pct"),
    ("ROA",              "roa",                  "pct"),
    ("Payout",           "payout",               "pct"),
]

# ── Dividends columns (from dividends.summary) ───────────────────────────────
# DPA + Div Yield here come from the dividends skill (B3 history + DVA), which
# may differ slightly from valuation's (price-based) — both are useful context.
_DIVIDENDS_COLS = [
    ("Eventos (B3)",         "event_count",      "int"),
    ("DPA (B3 médio)",       "b3_dpa_avg",       "brl_full"),
    ("Dividendos (últ ano)", "annual_dividendos", "brl"),
    ("JCP (últ ano)",        "annual_jcp",        "brl"),
    ("Total Remun. (últ a)", "annual_total",      "brl"),
]

# ── Summary mode: the ~10 KPIs for quick compare ─────────────────────────────
_SUMMARY_COLS = [
    ("Preço",         "price",          "brl_full"),
    ("Market Cap",    "market_cap",     "brl"),
    ("P/L",           "p_l",            "num"),
    ("P/VPA",         "p_vpa",          "num"),
    ("EV/EBITDA",     "ev_ebitda",      "num"),
    ("ROE",           "roe",            "pct"),
    ("Div Yield",     "dividend_yield", "pct"),
    ("Receita Líquida","receita_liquida","brl"),
    ("EBITDA",        "ebitda",         "brl"),
    ("Lucro Líquido", "lucro_liquido",  "brl"),
]

# ── Growth mode: QoQ + YoY % change ──────────────────────────────────────────
# Each entry: (column_label, dict_key, spec). dict_key is looked up in the
# growth dict returned by _compute_growth().
_GROWTH_COLS = [
    ("Receita QoQ",    "receita_qoq",    "pct_raw"),
    ("Receita YoY",    "receita_yoy",    "pct_raw"),
    ("EBITDA QoQ",     "ebitda_qoq",     "pct_raw"),
    ("EBITDA YoY",     "ebitda_yoy",     "pct_raw"),
    ("Lucro Liq. QoQ", "lucro_qoq",      "pct_raw"),
    ("Lucro Liq. YoY", "lucro_yoy",      "pct_raw"),
    ("Marg. EBITDA",   "marg_ebitda",    "pct"),
    ("ROE (TTM)",      "roe_ttm",        "pct"),
]


# ── Growth math ──────────────────────────────────────────────────────────────

def _compute_growth(financials_result: dict) -> dict:
    """Compute QoQ + YoY growth + TTM ratios from a financials.quarterly result.

    QoQ = (latest_quarter - prior_quarter) / |prior_quarter|
    YoY = (latest_quarter - same_quarter_last_year) / |same_quarter_last_year|

    Returns a flat dict with keys matching _GROWTH_COLS.
    """
    periods = financials_result.get("periods") or []
    ttm = financials_result.get("ttm") or {}

    out = {
        "receita_qoq": None, "receita_yoy": None,
        "ebitda_qoq": None, "ebitda_yoy": None,
        "lucro_qoq": None, "lucro_yoy": None,
        "marg_ebitda": None, "roe_ttm": None,
    }

    if not periods:
        return out

    # Sort newest-first by (year, quarter)
    sorted_p = sorted(periods,
                      key=lambda p: (p.get("year", 0), p.get("quarter", 0)),
                      reverse=True)

    latest = sorted_p[0] if sorted_p else {}
    latest_m = latest.get("metrics", {}) or {}

    # QoQ: latest vs the one right before it
    prior = sorted_p[1] if len(sorted_p) > 1 else {}
    prior_m = prior.get("metrics", {}) or {}

    out["receita_qoq"] = _pct_change(latest_m.get("receita_liquida"),
                                      prior_m.get("receita_liquida"))
    out["ebitda_qoq"] = _pct_change(latest_m.get("ebitda"),
                                     prior_m.get("ebitda"))
    out["lucro_qoq"] = _pct_change(latest_m.get("lucro_liquido"),
                                    prior_m.get("lucro_liquido"))

    # YoY: latest vs same quarter prior year (4 periods back)
    yoy_prior = sorted_p[4] if len(sorted_p) > 4 else {}
    yoy_m = yoy_prior.get("metrics", {}) or {}

    out["receita_yoy"] = _pct_change(latest_m.get("receita_liquida"),
                                      yoy_m.get("receita_liquida"))
    out["ebitda_yoy"] = _pct_change(latest_m.get("ebitda"),
                                     yoy_m.get("ebitda"))
    out["lucro_yoy"] = _pct_change(latest_m.get("lucro_liquido"),
                                    yoy_m.get("lucro_liquido"))

    # TTM ratios from the financials skill's TTM summary
    ttm_ratios = ttm.get("ratios", {}) or {}
    out["marg_ebitda"] = ttm_ratios.get("marg_ebitda")
    out["roe_ttm"] = ttm_ratios.get("roe")

    return out


def _pct_change(curr: float | None, prev: float | None) -> float | None:
    """Compute % change = (curr - prev) / |prev|.

    Returns None only when:
    - either value is None
    - prev is 0 or negative (can't compute meaningful % from non-positive base)
    - curr and prev have opposite signs (profit→loss or loss→profit — % is
      meaningless across a sign change)

    Extreme values (>500%) are NOT suppressed — they may be real (e.g. a company
    recovering from a tiny-base quarter). The LLM can judge whether the growth
    is meaningful. The sign-change guard alone catches the truly meaningless
    cases (the 3612% / -395% noise from v1.1 was caused by sign changes, not
    just magnitude).
    """
    if curr is None or prev is None:
        return None
    if prev <= 0:
        return None
    # Sign change: profit→loss or loss→profit — % growth is meaningless
    if curr * prev < 0:
        return None
    return (curr - prev) / abs(prev)
