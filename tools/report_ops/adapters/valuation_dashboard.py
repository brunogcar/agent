"""adapters/valuation_dashboard.py — Valuation dashboard adapter.

Takes a valuation.ratios() or valuation.summary() result and produces a
multi-tab dashboard payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<valuation result>,
         config={"adapter": "valuation_dashboard"})

Tabs produced:
  - Overview:      KPI cards (P/L, P/VPA, EV/EBITDA, Div Yield, Market Cap, ROE)
  - Multiples:     all price ratios (P/L, P/VPA, P/EBIT, P/FCO, P/FCF,
                    EV/EBITDA, EV/Sales, EV/FCF, PSR)
  - Profitability: ROE, ROA, ROIC, margins (gross/operating/net/EBITDA/OCF/FCF)
  - Liquidity & Leverage: current/quick/cash ratio, debt/equity, net debt/
                    EBITDA, interest coverage, cash flow to debt
  - Efficiency & Growth: asset/inventory/receivables/fixed asset turnover,
                    retention, sustainable growth, capex/revenue, effective
                    tax rate

This adapter is THIN — it consumes valuation.ratios()'s already-computed
ratios dict and groups the metrics into themed tabs. The ratios come from
two sources:
  1. Manual computation in valuation.ratios() (P/L, P/VPA, EV, PSR, DPA,
     Div Yield, market_cap, divida_liquida_ebitda) -- NOT in the calculations
     registry.
  2. compute_all_ratios() output (ROE, ROA, ROIC, margins, turnover, EV
     multiples, per_share, tax, etc.) -- all 37 calculations-backed metrics.

Both sources are merged into the same ratios dict by valuation.ratios(), so
this adapter simply reads from r["ratios"].
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)


# ── Multiples tab spec ───────────────────────────────────────────────────────
# (label, ratios_dict_key, format_spec)
_MULTIPLES = [
    ("P/L",       "p_l",        "num"),
    ("P/VPA",     "p_vpa",      "num"),
    ("P/EBIT",    "p_ebit",     "num"),
    ("P/FCO",     "p_fco",      "num"),
    ("P/FCF",     "p_fcf",      "num"),
    ("PSR",       "psr",        "num"),
    ("EV/EBITDA", "ev_ebitda",  "num"),
    ("EV/Sales",  "ev_sales",   "num"),
    ("EV/FCF",    "ev_fcf",     "num"),
]

# ── Profitability tab spec ───────────────────────────────────────────────────
_PROFITABILITY = [
    ("ROE",             "roe",              "pct"),
    ("ROA",             "roa",              "pct"),
    ("ROIC",            "roic",             "pct"),
    ("Marg. Bruta",     "gross_margin",     "pct"),
    ("Marg. Operac.",   "operating_margin", "pct"),
    ("Marg. Líquida",   "net_margin",       "pct"),
    ("Marg. EBITDA",    "ebitda_margin",    "pct"),
    ("Marg. FCO",       "ocf_margin",       "pct"),
    ("Marg. FCF",       "fcf_margin",       "pct"),
    ("Graham Number",   "graham_number",    "brl_full"),
    ("P/VPA Tangível",  "price_to_tangible_book", "num"),
]

# ── Liquidity & Leverage tab spec ────────────────────────────────────────────
_LIQUIDITY_LEVERAGE = [
    ("Liquidez Corrente",  "current_ratio",      "num"),
    ("Liquidez Seca",      "quick_ratio",        "num"),
    ("Liquidez Imediata",  "cash_ratio",         "num"),
    ("Capital de Giro",    "working_capital",    "brl"),
    ("Dívida/PL",          "debt_equity",        "pct"),
    ("Dív. Líq/EBITDA",    "net_debt_ebitda",    "num"),
    ("Cobertura Juros",    "interest_coverage",  "num"),
    ("FCO/Dívida",         "cash_flow_to_debt",  "pct"),
    ("Dív. Líq/EBITDA (manual)", "divida_liquida_ebitda", "num"),
]

# ── Efficiency & Growth tab spec ─────────────────────────────────────────────
_EFFICIENCY_GROWTH = [
    ("Giro do Ativo",            "asset_turnover",        "num"),
    ("Giro Estoque",             "inventory_turnover",    "num"),
    ("Giro Contas a Receber",    "receivables_turnover",  "num"),
    ("Giro Imobilizado",         "fixed_asset_turnover",  "num"),
    ("Capex/Receita",            "capex_revenue",         "pct"),
    ("Taxa de Retenção",         "retention_ratio",       "pct"),
    ("Crescimento Sustentável",  "sustainable_growth",    "pct"),
    ("Taxa de Tributo Efetiva",  "effective_tax_rate",    "pct"),
]


def _kv_table_section(title: str, rows: list[tuple[str, Any, str]]) -> dict:
    """Build a key-value table section: 2 columns (Indicador, Valor)."""
    from tools.report_ops.formats import apply_fmt
    return {
        "title": title,
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [[label, apply_fmt(_safe_num(value), spec)] for label, value, spec in rows],
        "formats": {"Indicador": "text", "Valor": "text"},
    }


def _metrics_section(title: str, ratios: dict,
                     specs: list[tuple[str, str, str]]) -> dict:
    """Build a key-value table from ratios dict + a (label, key, spec) list."""
    rows = [(label, ratios.get(key), spec) for label, key, spec in specs]
    return _kv_table_section(title, rows)


def _kpis(ratios: dict) -> list[dict]:
    """Build the top-level KPI cards for the Overview tab."""
    from tools.report_ops.formats import apply_fmt
    return [
        {"label": "P/L",         "value": apply_fmt(_safe_num(ratios.get("p_l")),       "num")},
        {"label": "P/VPA",       "value": apply_fmt(_safe_num(ratios.get("p_vpa")),     "num")},
        {"label": "EV/EBITDA",   "value": apply_fmt(_safe_num(ratios.get("ev_ebitda")), "num")},
        {"label": "Div Yield",   "value": apply_fmt(_safe_num(ratios.get("dividend_yield")), "pct")},
        {"label": "Market Cap",  "value": apply_fmt(_safe_num(ratios.get("market_cap")), "brl")},
        {"label": "ROE",         "value": apply_fmt(_safe_num(ratios.get("roe")),       "pct")},
    ]


def _overview_section(ratios: dict) -> dict:
    """Build a key-value table of headline metrics for the Overview tab."""
    rows = [
        ("Preço",              ratios.get("price"),       "brl_full"),
        ("Data do Preço",      ratios.get("price_date"),  "text"),
        ("Fonte do Preço",     ratios.get("price_source"),"text"),
        ("Total de Ações",     ratios.get("total_shares"),"int"),
        ("Market Cap",         ratios.get("market_cap"),  "brl"),
        ("EV",                  ratios.get("ev"),          "brl"),
        ("EBITDA (TTM)",       ratios.get("ebitda"),      "brl"),
        ("Lucro Líquido (TTM)",ratios.get("lucro_liquido"),"brl"),
        ("Receita Líquida (TTM)", ratios.get("receita_liquida"), "brl"),
        ("Patrimônio Líquido", ratios.get("patrimonio_liquido"), "brl"),
        ("Dívida Bruta",       ratios.get("divida_bruta"), "brl"),
        ("Caixa",              ratios.get("caixa"),        "brl"),
        ("P/L",                ratios.get("p_l"),          "num"),
        ("P/VPA",              ratios.get("p_vpa"),        "num"),
        ("EV/EBITDA",          ratios.get("ev_ebitda"),    "num"),
        ("Dividend Yield",     ratios.get("dividend_yield"),"pct"),
        ("DPA (TTM)",          ratios.get("dpa"),          "brl_full"),
        ("ROE",                ratios.get("roe"),          "pct"),
        ("ROA",                ratios.get("roa"),          "pct"),
        ("ROIC",               ratios.get("roic"),         "pct"),
    ]
    return _kv_table_section("Overview", rows)


def _availability_section(result: dict) -> dict:
    """Build a small table showing data source availability (from summary())."""
    da = result.get("data_availability") or {}
    if not da:
        return {
            "title": "Data Source Availability",
            "type": "table",
            "columns": ["Source", "Status"],
            "rows": [],
            "formats": {"Source": "text", "Status": "text"},
            "note": "data_availability block not present (call summary() to populate).",
        }
    rows = [[k, str(v)] for k, v in da.items()]
    return {
        "title": "Data Source Availability",
        "type": "table",
        "columns": ["Source", "Status"],
        "rows": rows,
        "formats": {"Source": "text", "Status": "text"},
    }


# ── Adapter entry point ──────────────────────────────────────────────────────

@register_adapter("valuation_dashboard")
def valuation_dashboard(result: dict) -> dict:
    """Flatten valuation.ratios() / valuation.summary() / valuation.dashboard()
    result into a multi-tab dashboard payload.

    If the input already has a 'tabs' key (from valuation.dashboard() mode),
    pass through as-is — the dashboard mode already shapes the data correctly.
    """
    if not _ok(result):
        return _error_table(result, title="Valuation Dashboard")

    # If dashboard() mode was called, the result already has tabs — pass through.
    if result.get("tabs"):
        return result

    ratios = result.get("ratios") or {}
    if not ratios:
        return _error_table(result, title="Valuation Dashboard")

    # ── Tab 1: Overview ────────────────────────────────────────────────────
    overview_sections = [_overview_section(ratios)]
    # If summary() was called, also surface the data_availability block.
    if result.get("data_availability"):
        overview_sections.append(_availability_section(result))

    # ── Tab 2: Multiples ───────────────────────────────────────────────────
    multiples_sections = [_metrics_section("Price Multiples", ratios, _MULTIPLES)]

    # ── Tab 3: Profitability ───────────────────────────────────────────────
    profitability_sections = [
        _metrics_section("Profitability & Margins", ratios, _PROFITABILITY),
    ]

    # ── Tab 4: Liquidity & Leverage ────────────────────────────────────────
    liquidity_sections = [
        _metrics_section("Liquidity & Leverage", ratios, _LIQUIDITY_LEVERAGE),
    ]

    # ── Tab 5: Efficiency & Growth ─────────────────────────────────────────
    efficiency_sections = [
        _metrics_section("Efficiency, Growth & Tax", ratios, _EFFICIENCY_GROWTH),
    ]

    tabs = [
        {"name": "Overview",                "sections": overview_sections},
        {"name": "Multiples",               "sections": multiples_sections},
        {"name": "Profitability",           "sections": profitability_sections},
        {"name": "Liquidity & Leverage",    "sections": liquidity_sections},
        {"name": "Efficiency & Growth",     "sections": efficiency_sections},
    ]

    return {
        "company": result.get("ticker", ""),
        "tabs": tabs,
        "kpis": _kpis(ratios),
        "sources": [],
    }
