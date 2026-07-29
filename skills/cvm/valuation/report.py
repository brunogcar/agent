"""skills/cvm/valuation/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the ratios dict into a multi-tab dashboard payload.

Each builder produces a section dict with the correct shape for the dashboard
template:
  - Table sections: {"type": "table", "title": ..., "columns": [...], "rows": [...]}
  - Ratio grid sections: {"type": "ratio_grid", "title": ..., "categories": [...]}

The KPI cards are produced separately (build_overview_kpis) and placed at the
top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


# ── Ratio key -> (label, format_spec) tuples per tab ──────────────────────────

_MULTIPLES_ITEMS: list[tuple[str, str, str]] = [
    ("P/L",              "p_l",                  "num"),
    ("P/VPA",            "p_vpa",                "num"),
    ("P/EBIT",           "p_ebit",               "num"),
    ("P/FCO",            "p_fco",                "num"),
    ("P/FCF",            "p_fcf",                "num"),
    ("EV/EBITDA",        "ev_ebitda",            "num"),
    ("EV/Sales",         "ev_sales",             "num"),
    ("EV/FCF",           "ev_fcf",               "num"),
    ("PSR",              "psr",                  "num"),
    ("Graham Number",    "graham_number",        "brl_full"),
    ("P/Tangible Book",  "price_to_tangible_book", "num"),
]

_PROFITABILITY_ITEMS: list[tuple[str, str, str]] = [
    ("ROE",                 "roe",              "pct"),
    ("ROA",                 "roa",              "pct"),
    ("ROIC",                "roic",             "pct"),
    ("Gross Margin",        "gross_margin",     "pct"),
    ("Operating Margin",    "operating_margin", "pct"),
    ("Net Margin",          "net_margin",       "pct"),
    ("EBITDA Margin",       "ebitda_margin",    "pct"),
    ("OCF Margin",          "ocf_margin",       "pct"),
    ("FCF Margin",          "fcf_margin",       "pct"),
    ("Effective Tax Rate",  "effective_tax_rate", "pct"),
]

_LIQUIDITY_LEVERAGE_ITEMS: list[tuple[str, str, str]] = [
    ("Current Ratio",       "current_ratio",       "num"),
    ("Quick Ratio",         "quick_ratio",         "num"),
    ("Cash Ratio",          "cash_ratio",          "num"),
    ("Working Capital",     "working_capital",     "brl"),
    ("Debt/Equity",         "debt_equity",         "pct"),
    ("Net Debt/EBITDA",     "net_debt_ebitda",     "num"),
    ("Cash Flow to Debt",   "cash_flow_to_debt",   "pct"),
    ("Interest Coverage",   "interest_coverage",   "num"),
]

_EFFICIENCY_GROWTH_ITEMS: list[tuple[str, str, str]] = [
    ("Asset Turnover",         "asset_turnover",       "num"),
    ("Inventory Turnover",     "inventory_turnover",   "num"),
    ("Receivables Turnover",   "receivables_turnover", "num"),
    ("Fixed Asset Turnover",   "fixed_asset_turnover", "num"),
    ("CapEx/Revenue",          "capex_revenue",        "pct"),
    ("Retention Ratio",        "retention_ratio",      "pct"),
    ("Sustainable Growth",     "sustainable_growth",   "pct"),
]


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _safe_get(ratios_dict: dict | None, key: str) -> Any:
    """Pull a key from ratios_dict, returning None when missing."""
    if not isinstance(ratios_dict, dict):
        return None
    return ratios_dict.get(key)


def _fmt(value: Any, spec: str) -> str:
    """Format a value using apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


# ── KPI cards (top-level, not inside a section) ──────────────────────────────

def build_overview_kpis(ratios_dict: dict | None) -> list[dict]:
    """Build the 6 KPI cards for the dashboard top-level kpis list."""
    return [
        {"label": "P/L",            "value": _fmt(_safe_get(ratios_dict, "p_l"),            "num")},
        {"label": "P/VPA",          "value": _fmt(_safe_get(ratios_dict, "p_vpa"),          "num")},
        {"label": "EV/EBITDA",      "value": _fmt(_safe_get(ratios_dict, "ev_ebitda"),      "num")},
        {"label": "Div Yield",      "value": _fmt(_safe_get(ratios_dict, "dividend_yield"), "pct")},
        {"label": "Market Cap",     "value": _fmt(_safe_get(ratios_dict, "market_cap"),     "brl")},
        {"label": "ROE",            "value": _fmt(_safe_get(ratios_dict, "roe"),            "pct")},
    ]


# ── Overview tab sections ────────────────────────────────────────────────────

def build_overview_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Overview tab sections as a table of headline metrics."""
    rows = [
        ("Preço",              _fmt(_safe_get(ratios_dict, "price"),              "brl_full")),
        ("Data do Preço",      str(_safe_get(ratios_dict, "price_date")  or "—")),
        ("Fonte do Preço",     str(_safe_get(ratios_dict, "price_source") or "—")),
        ("Total de Ações",     _fmt(_safe_get(ratios_dict, "total_shares"),       "int")),
        ("Market Cap",         _fmt(_safe_get(ratios_dict, "market_cap"),         "brl")),
        ("EV",                 _fmt(_safe_get(ratios_dict, "ev"),                 "brl")),
        ("EBITDA (TTM)",       _fmt(_safe_get(ratios_dict, "ebitda"),             "brl")),
        ("Lucro Líquido (TTM)",_fmt(_safe_get(ratios_dict, "lucro_liquido"),      "brl")),
        ("Receita Líquida",    _fmt(_safe_get(ratios_dict, "receita_liquida"),    "brl")),
        ("Patrimônio Líquido", _fmt(_safe_get(ratios_dict, "patrimonio_liquido"), "brl")),
        ("Dívida Bruta",       _fmt(_safe_get(ratios_dict, "divida_bruta"),       "brl")),
        ("Caixa",              _fmt(_safe_get(ratios_dict, "caixa"),              "brl")),
        ("P/L",                _fmt(_safe_get(ratios_dict, "p_l"),                "num")),
        ("P/VPA",              _fmt(_safe_get(ratios_dict, "p_vpa"),              "num")),
        ("EV/EBITDA",          _fmt(_safe_get(ratios_dict, "ev_ebitda"),          "num")),
        ("Dividend Yield",     _fmt(_safe_get(ratios_dict, "dividend_yield"),     "pct")),
        ("DPA (TTM)",          _fmt(_safe_get(ratios_dict, "dpa"),                "brl_full")),
        ("ROE",                _fmt(_safe_get(ratios_dict, "roe"),                "pct")),
        ("ROA",                _fmt(_safe_get(ratios_dict, "roa"),                "pct")),
        ("ROIC",               _fmt(_safe_get(ratios_dict, "roic"),               "pct")),
    ]
    return [{
        "title": "Key Metrics",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    }]


# ── Ratio grid section builder (used by tabs 2-5) ────────────────────────────

def _build_table_section(
    title: str,
    items: list[tuple[str, str, str]],
    ratios_dict: dict | None,
) -> dict:
    """Build a table section with 2 columns (Indicador, Valor).

    Uses apply_fmt for proper BRL/pct/num formatting.
    """
    rows = [
        [label, _fmt(_safe_get(ratios_dict, key), spec)]
        for label, key, spec in items
    ]
    return {
        "title": title,
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    }


def build_multiples_section(ratios_dict: dict | None) -> dict:
    """Build the Multiples tab section."""
    return _build_table_section("Price Multiples", _MULTIPLES_ITEMS, ratios_dict)


def build_profitability_section(ratios_dict: dict | None) -> dict:
    """Build the Profitability tab section."""
    return _build_table_section("Profitability & Margins", _PROFITABILITY_ITEMS, ratios_dict)


def build_liquidity_leverage_section(ratios_dict: dict | None) -> dict:
    """Build the Liquidity & Leverage tab section."""
    return _build_table_section("Liquidity & Leverage", _LIQUIDITY_LEVERAGE_ITEMS, ratios_dict)


def build_efficiency_growth_section(ratios_dict: dict | None) -> dict:
    """Build the Efficiency & Growth tab section."""
    return _build_table_section("Efficiency, Growth & Tax", _EFFICIENCY_GROWTH_ITEMS, ratios_dict)
