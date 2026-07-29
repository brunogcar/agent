"""skills/cvm/valuation/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the ratios dict into a multi-tab dashboard payload (Overview /
Multiples / Profitability / Liquidity & Leverage / Efficiency & Growth).

Each builder takes the ratios dict (as returned by `ratios()` mode's
`result["ratios"]` block) and returns a section dict ready for tab
assembly. Keeping these helpers separate from modes/dashboard.py keeps
the dashboard mode file under 300 lines and makes the section layout
reusable should a future mode want to embed (e.g.) just the Multiples tab.

Public functions:
  - build_overview_kpis        : 6 KPI cards for the Overview tab.
  - build_overview_sections    : Overview tab sections (kpis + freshness).
  - build_ratio_grid_section   : ratio_grid section with label/value/unit items.
  - build_multiples_section    : Multiples tab section (price ratios + Graham).
  - build_profitability_section: Profitability tab section (ROE/ROA/ROIC + margins + tax).
  - build_liquidity_leverage_section : Liquidity & Leverage tab section.
  - build_efficiency_growth_section  : Efficiency & Growth tab section.
"""
from __future__ import annotations

from typing import Any


# ── Ratio key -> (label, unit) tuples per tab ────────────────────────────────
# These are the canonical English registry keys for calculations-backed
# metrics + the manual keys (p_l, p_vpa, ev, psr, dividend_yield,
# divida_liquida_ebitda, market_cap) that are NOT in the calculations
# registry. The label is what gets surfaced in the dashboard payload.

_MULTIPLES_ITEMS: list[tuple[str, str, str]] = [
    ("P/L",              "p_l",                  "x"),
    ("P/VPA",            "p_vpa",                "x"),
    ("P/EBIT",           "p_ebit",               "x"),
    ("P/FCO",            "p_fco",                "x"),
    ("P/FCF",            "p_fcf",                "x"),
    ("EV/EBITDA",        "ev_ebitda",            "x"),
    ("EV/Sales",         "ev_sales",             "x"),
    ("EV/FCF",           "ev_fcf",               "x"),
    ("PSR",              "psr",                  "x"),
    ("Graham Number",    "graham_number",        "BRL"),
    ("P/Tangible Book",  "price_to_tangible_book", "x"),
]

_PROFITABILITY_ITEMS: list[tuple[str, str, str]] = [
    ("ROE",                 "roe",              "ratio"),
    ("ROA",                 "roa",              "ratio"),
    ("ROIC",                "roic",             "ratio"),
    ("Gross Margin",        "gross_margin",     "ratio"),
    ("Operating Margin",    "operating_margin", "ratio"),
    ("Net Margin",          "net_margin",       "ratio"),
    ("EBITDA Margin",       "ebitda_margin",    "ratio"),
    ("OCF Margin",          "ocf_margin",       "ratio"),
    ("FCF Margin",          "fcf_margin",       "ratio"),
    ("Effective Tax Rate",  "effective_tax_rate", "ratio"),
]

_LIQUIDITY_LEVERAGE_ITEMS: list[tuple[str, str, str]] = [
    # Liquidity
    ("Current Ratio",       "current_ratio",       "x"),
    ("Quick Ratio",         "quick_ratio",         "x"),
    ("Cash Ratio",          "cash_ratio",          "x"),
    ("Working Capital",     "working_capital",     "BRL"),
    # Leverage
    ("Debt/Equity",         "debt_equity",         "ratio"),
    ("Net Debt/EBITDA",     "net_debt_ebitda",     "x"),
    ("Cash Flow to Debt",   "cash_flow_to_debt",   "ratio"),
    ("Interest Coverage",   "interest_coverage",   "x"),
]

_EFFICIENCY_GROWTH_ITEMS: list[tuple[str, str, str]] = [
    # Efficiency
    ("Asset Turnover",         "asset_turnover",       "ratio"),
    ("Inventory Turnover",     "inventory_turnover",   "x"),
    ("Receivables Turnover",   "receivables_turnover", "x"),
    ("Fixed Asset Turnover",   "fixed_asset_turnover", "ratio"),
    ("CapEx/Revenue",          "capex_revenue",        "ratio"),
    # Growth
    ("Retention Ratio",        "retention_ratio",      "ratio"),
    ("Sustainable Growth",     "sustainable_growth",   "ratio"),
]


# ── Safe accessor ────────────────────────────────────────────────────────────

def _safe_get(ratios_dict: dict | None, key: str) -> Any:
    """Pull a key from ratios_dict, returning None when dict is missing or
    the key is absent.

    Defensive against the case where `ratios()` returned status=error /
    partial and `result["ratios"]` is `{"status": "error", ...}` (no actual
    ratio keys) — every `.get(key)` returns None and the dashboard payload
    still builds successfully with all-None values.
    """
    if not isinstance(ratios_dict, dict):
        return None
    return ratios_dict.get(key)


# ── Tab 1: Overview ──────────────────────────────────────────────────────────

def build_overview_kpis(ratios_dict: dict | None) -> list[dict]:
    """Build the 6 KPI cards for the Overview tab.

    The KPI labels + units are fixed per the dashboard spec:
      P/L (x) / P/VPA (x) / EV/EBITDA (x) /
      Dividend Yield (ratio) / Market Cap (BRL) / ROE (ratio).
    """
    return [
        {"label": "P/L",             "value": _safe_get(ratios_dict, "p_l"),             "unit": "x"},
        {"label": "P/VPA",           "value": _safe_get(ratios_dict, "p_vpa"),           "unit": "x"},
        {"label": "EV/EBITDA",       "value": _safe_get(ratios_dict, "ev_ebitda"),       "unit": "x"},
        {"label": "Dividend Yield",  "value": _safe_get(ratios_dict, "dividend_yield"),  "unit": "ratio"},
        {"label": "Market Cap",      "value": _safe_get(ratios_dict, "market_cap"),      "unit": "BRL"},
        {"label": "ROE",             "value": _safe_get(ratios_dict, "roe"),             "unit": "ratio"},
    ]


def build_overview_sections(ratios_dict: dict | None, kpis: list[dict]) -> list[dict]:
    """Build the Overview tab sections (kpis + freshness metadata).

    The freshness section is best-effort — if skills.cvm._freshness can't
    be imported or add_freshness raises, the section is silently omitted.
    """
    overview_sections: list[dict] = [
        {"name": "kpis", "cards": kpis},
        {"name": "price", "data": {
            "price":       _safe_get(ratios_dict, "price"),
            "price_date":  _safe_get(ratios_dict, "price_date"),
            "price_source": _safe_get(ratios_dict, "price_source"),
        }},
    ]
    # Attach freshness metadata if available (best-effort).
    try:
        from skills.cvm._freshness import add_freshness
        overview_sections.append({"name": "freshness",
                                  "data": add_freshness({})["data_freshness"]})
    except Exception:
        pass
    return overview_sections


# ── Generic ratio_grid section builder ───────────────────────────────────────

def build_ratio_grid_section(
    items: list[tuple[str, str, str]],
    ratios_dict: dict | None,
) -> dict:
    """Build a ratio_grid section from a list of (label, key, unit) tuples.

    Returns a dict shaped as ``{"name": "ratio_grid", "items": [...]}`` where
    each item is ``{"label": str, "value": float|None, "unit": str}``. Missing
    ratios produce ``value: None`` — the dashboard payload still builds.
    """
    return {
        "name": "ratio_grid",
        "items": [
            {"label": label,
             "value": _safe_get(ratios_dict, key),
             "unit": unit}
            for label, key, unit in items
        ],
    }


# ── Tab 2: Multiples ─────────────────────────────────────────────────────────

def build_multiples_section(ratios_dict: dict | None) -> dict:
    """Build the Multiples tab section: all price ratios + Graham Number +
    P/Tangible Book. Mixes manual keys (p_l, p_vpa, psr) with calculations-
    backed keys (p_ebit, p_fco, p_fcf, ev_ebitda, ev_sales, ev_fcf,
    graham_number, price_to_tangible_book).
    """
    return build_ratio_grid_section(_MULTIPLES_ITEMS, ratios_dict)


# ── Tab 3: Profitability ─────────────────────────────────────────────────────

def build_profitability_section(ratios_dict: dict | None) -> dict:
    """Build the Profitability tab section: ROE/ROA/ROIC + 6 margins +
    Effective Tax Rate. All keys come from the calculations registry.
    """
    return build_ratio_grid_section(_PROFITABILITY_ITEMS, ratios_dict)


# ── Tab 4: Liquidity & Leverage ──────────────────────────────────────────────

def build_liquidity_leverage_section(ratios_dict: dict | None) -> dict:
    """Build the Liquidity & Leverage tab section: 4 liquidity ratios
    (current/quick/cash + working capital) + 4 leverage ratios (D/E,
    Net Debt/EBITDA, Cash Flow to Debt, Interest Coverage).
    """
    return build_ratio_grid_section(_LIQUIDITY_LEVERAGE_ITEMS, ratios_dict)


# ── Tab 5: Efficiency & Growth ───────────────────────────────────────────────

def build_efficiency_growth_section(ratios_dict: dict | None) -> dict:
    """Build the Efficiency & Growth tab section: 5 efficiency ratios
    (asset/inventory/receivables/fixed-asset turnover + CapEx/Revenue) +
    2 growth ratios (Retention Ratio, Sustainable Growth).
    """
    return build_ratio_grid_section(_EFFICIENCY_GROWTH_ITEMS, ratios_dict)
