"""skills/cvm/valuation/report.py -- Dashboard composition helpers.

[v1.5] Reorganized for the 6-tab valuation dashboard (Overview / Multiples /
Per-share / Profitability / Liquidity & Leverage / Efficiency & Growth).
Each builder returns a section dict shaped for the dashboard template:

  {"type": "table",      "title": ..., "columns": [...], "rows": [...]}
  {"type": "ratio_grid", "title": ..., "categories": [{label, items}]}
  {"type": "chart",      "chart_data": {type, data, options}}
  {"type": "subtabs",    "tabs": [{name, sections}]}
  {"type": "collapsible","title": ..., "text": ..., "open": False}
  {"type": "text",       "text": ...}

KPIs (top-level) are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (`result["kpis"]`).

Design rules:
  - Call ratios() ONCE in the dashboard mode + pass the ratios dict to every
    builder. No builder makes its own data-fetching call.
  - Each builder tolerates None values gracefully (renders "—").
  - Each builder is independently try/except-wrapped by the dashboard mode
    so a failure in one tab degrades to an error section, not a crash.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


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


def _safe_div(a: Any, b: Any) -> float | None:
    """Divide a/b, returning None when either side is None or b is zero."""
    if a is None or b is None or b == 0:
        return None
    try:
        return a / b
    except (TypeError, ValueError, ZeroDivisionError):
        return None


# ── KPI cards (top-level, not inside a section) ──────────────────────────────

def build_overview_kpis(ratios_dict: dict | None) -> list[dict]:
    """Build the 6 KPI cards for the dashboard top-level kpis list."""
    return [
        {"label": "P/L",            "value": _fmt(_safe_get(ratios_dict, "p_l"),            "num")},
        {"label": "P/VPA",          "value": _fmt(_safe_get(ratios_dict, "p_vpa"),          "num")},
        {"label": "EV/EBITDA",      "value": _fmt(_safe_get(ratios_dict, "ev_ebitda"),      "num")},
        {"label": "Dividend Yield", "value": _fmt(_safe_get(ratios_dict, "dividend_yield"), "pct")},
        {"label": "Market Cap",     "value": _fmt(_safe_get(ratios_dict, "market_cap"),     "brl")},
        {"label": "ROE",            "value": _fmt(_safe_get(ratios_dict, "roe"),            "pct")},
    ]


# ── Tab 1: Overview -- summary text + price details collapsible ──────────────

def build_overview_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Overview tab sections: summary text + price details collapsible.

    The tab keeps the headline metrics table (Preço, Market Cap, EV, EBITDA,
    fundamental per-share values, headline ratios) and adds a collapsible
    "Price Details" section with price, date, source, and total shares.
    """
    sections: list[dict] = []

    # ── Summary table of headline metrics ──
    rows = [
        ["Preço",              _fmt(_safe_get(ratios_dict, "price"),              "brl_full")],
        ["Data do Preço",      str(_safe_get(ratios_dict, "price_date")  or "—")],
        ["Fonte do Preço",     str(_safe_get(ratios_dict, "price_source") or "—")],
        ["Total de Ações",     _fmt(_safe_get(ratios_dict, "total_shares"),       "int")],
        ["Market Cap",         _fmt(_safe_get(ratios_dict, "market_cap"),         "brl")],
        ["EV",                 _fmt(_safe_get(ratios_dict, "ev"),                 "brl")],
        ["EBITDA (TTM)",       _fmt(_safe_get(ratios_dict, "ebitda"),             "brl")],
        ["Lucro Líquido (TTM)",_fmt(_safe_get(ratios_dict, "lucro_liquido"),      "brl")],
        ["Receita Líquida",    _fmt(_safe_get(ratios_dict, "receita_liquida"),    "brl")],
        ["Patrimônio Líquido", _fmt(_safe_get(ratios_dict, "patrimonio_liquido"), "brl")],
        ["Dívida Bruta",       _fmt(_safe_get(ratios_dict, "divida_bruta"),       "brl")],
        ["Caixa",              _fmt(_safe_get(ratios_dict, "caixa"),              "brl")],
        ["P/L",                _fmt(_safe_get(ratios_dict, "p_l"),                "num")],
        ["P/VPA",              _fmt(_safe_get(ratios_dict, "p_vpa"),              "num")],
        ["EV/EBITDA",          _fmt(_safe_get(ratios_dict, "ev_ebitda"),          "num")],
        ["Dividend Yield",     _fmt(_safe_get(ratios_dict, "dividend_yield"),     "pct")],
        ["DPA (TTM)",          _fmt(_safe_get(ratios_dict, "dpa"),                "brl_full")],
        ["ROE",                _fmt(_safe_get(ratios_dict, "roe"),                "pct")],
        ["ROA",                _fmt(_safe_get(ratios_dict, "roa"),                "pct")],
        ["ROIC",               _fmt(_safe_get(ratios_dict, "roic"),               "pct")],
    ]
    sections.append({
        "title": "Key Metrics",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    })

    # ── Collapsible: Price Details ──
    price      = _fmt(_safe_get(ratios_dict, "price"),        "brl_full")
    price_date = str(_safe_get(ratios_dict, "price_date")  or "—")
    price_src  = str(_safe_get(ratios_dict, "price_source") or "—")
    shares     = _fmt(_safe_get(ratios_dict, "total_shares"), "int")
    mcap       = _fmt(_safe_get(ratios_dict, "market_cap"),   "brl")
    mcap_src   = str(_safe_get(ratios_dict, "market_cap_source") or "—")
    unit       = str(_safe_get(ratios_dict, "unit_ticker") or "—")
    detail_lines = [
        f"Preço: {price}",
        f"Data do Preço: {price_date}",
        f"Fonte do Preço: {price_src}",
        f"Total de Ações: {shares}",
        f"Market Cap: {mcap}",
        f"Market Cap (fonte): {mcap_src}",
        f"UNIT ticker: {unit}",
    ]
    sections.append({
        "type": "collapsible",
        "title": "Price Details",
        "text": " | ".join(detail_lines),
        "open": False,
    })

    return sections


# ── Tab 2: Multiples -- table + chart + collapsible ──────────────────────────

# Top 10 most-common multiples (main table). Each tuple is:
#   (label, key, fmt_spec, interpretation_template)
# `key` is the ratios_dict key; for derived metrics (P/EBITDA, EV/EBIT, P/EV),
# we compute from components via _safe_div in the builder.
_MULTIPLES_TOP: list[tuple[str, str, str, str]] = [
    ("P/L",       "p_l",       "num", "Cheap if < 10; expensive if > 25"),
    ("P/VPA",     "p_vpa",     "num", "Cheap if < 1; expensive if > 3"),
    ("P/EBIT",    "p_ebit",    "num", "Cheap if < 8; expensive if > 20"),
    ("P/EBITDA",  "p_ebitda",  "num", "Cheap if < 8; expensive if > 15"),
    ("EV/EBIT",   "ev_ebit",   "num", "Cheap if < 8; expensive if > 15"),
    ("EV/EBITDA", "ev_ebitda", "num", "Cheap if < 8; expensive if > 15"),
    ("PSR",       "psr",       "num", "Cheap if < 1; expensive if > 3"),
    ("P/EV",      "p_ev",      "num", "Cheap if < 1; expensive if > 3"),
    ("P/FCO",     "p_fco",     "num", "Cheap if < 10; expensive if > 25"),
    ("P/FCF",     "p_fcf",     "num", "Cheap if < 15; expensive if > 30"),
]

# Less-common multiples (collapsible). Key is ratios_dict key — when missing,
# we attempt to compute from components in the builder.
_MULTIPLES_LESS_COMMON: list[tuple[str, str, str, str]] = [
    ("P/Ativos",        "p_ativos",   "num", "Cheap if < 1; expensive if > 2"),
    ("P/Passivos",      "p_passivos", "num", "Higher = more leveraged"),
    ("P/RB",            "p_rb",       "num", "Cheap if < 1; expensive if > 3"),
    ("P/CG",            "p_cg",       "num", "Higher = pricier vs working capital"),
    ("P/DB",            "p_db",       "num", "Higher = pricier vs gross debt"),
    ("P/Tangible Book", "price_to_tangible_book", "num", "Cheap if < 1; expensive if > 3"),
]

# Multiples shown in the comparison bar chart (raw values, no normalization).
_MULTIPLES_CHART: list[tuple[str, str]] = [
    ("P/L",       "p_l"),
    ("P/VPA",     "p_vpa"),
    ("EV/EBITDA", "ev_ebitda"),
    ("PSR",       "psr"),
]

_MULTIPLES_CHART_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7"]


def _derive_multiples(ratios_dict: dict | None) -> dict[str, float | None]:
    """Compute multiples NOT directly stored in ratios_dict.

    These are derived from components that ARE in ratios_dict:
      - p_ebitda = market_cap / ebitda
      - ev_ebit  = ev / ebit
      - p_ev     = market_cap / ev
      - p_cg     = market_cap / working_capital
      - p_db     = market_cap / divida_bruta
      - p_ativos, p_passivos, p_rb = NOT derivable (total_assets, total_liab,
        gross_revenue not in ratios_dict) — return None, surface as '—'.

    Returns a dict {metric_key: value_or_None} suitable for merging with
    ratios_dict via _safe_get-style accessors.
    """
    if not isinstance(ratios_dict, dict):
        return {}

    market_cap = ratios_dict.get("market_cap")
    ev         = ratios_dict.get("ev")
    ebit       = ratios_dict.get("ebit")
    ebitda     = ratios_dict.get("ebitda")
    wc         = ratios_dict.get("working_capital")
    db         = ratios_dict.get("divida_bruta")

    return {
        "p_ebitda":   _safe_div(market_cap, ebitda),
        "ev_ebit":    _safe_div(ev, ebit),
        "p_ev":       _safe_div(market_cap, ev),
        "p_cg":       _safe_div(market_cap, wc),
        "p_db":       _safe_div(market_cap, db),
        # p_ativos, p_passivos, p_rb NOT derivable — left as None.
        "p_ativos":   None,
        "p_passivos": None,
        "p_rb":       None,
    }


def build_multiples_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Multiples tab sections.

    Returns 3 sections:
      1. Top-10 multiples table [Métrica, Valor, Interpretação]
      2. Bar chart comparing P/L, P/VPA, EV/EBITDA, PSR
      3. Collapsible "Less Common Multiples" with 6 less-common metrics
    """
    sections: list[dict] = []
    derived = _derive_multiples(ratios_dict)

    def _lookup(key: str) -> Any:
        """Read from ratios_dict first, fall back to derived multiples."""
        v = _safe_get(ratios_dict, key)
        if v is None:
            v = derived.get(key)
        return v

    # ── Section 1: Top-10 multiples table ──
    rows: list[list[str]] = []
    for label, key, spec, interp in _MULTIPLES_TOP:
        value = _lookup(key)
        rows.append([label, _fmt(value, spec), interp if value is not None else "—"])
    sections.append({
        "title": "Top Price Multiples",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": rows,
        "note": (
            "Interpretation is a generic rule-of-thumb — sector context matters. "
            "Negative/zero denominators yield '—'."
        ),
    })

    # ── Section 2: Bar chart comparing headline multiples ──
    chart_labels: list[str] = []
    chart_data: list[float | None] = []
    for label, key in _MULTIPLES_CHART:
        chart_labels.append(label)
        chart_data.append(_lookup(key))
    if any(v is not None for v in chart_data):
        sections.append({
            "type": "chart",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": chart_labels,
                    "datasets": [{
                        "label": "Multiples",
                        "data": [v if v is not None else 0 for v in chart_data],
                        "backgroundColor": _MULTIPLES_CHART_COLORS[:len(chart_labels)],
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "y": {"beginAtZero": True},
                    },
                    "plugins": {
                        "legend": {"display": False},
                    },
                },
            },
        })

    # ── Section 3: Collapsible "Less Common Multiples" ──
    parts: list[str] = []
    for label, key, spec, _interp in _MULTIPLES_LESS_COMMON:
        value = _lookup(key)
        parts.append(f"{label}: {_fmt(value, spec)}")
    sections.append({
        "type": "collapsible",
        "title": "Less Common Multiples",
        "text": " | ".join(parts),
        "open": False,
    })

    return sections


# ── Tab 3: Per-share -- table + bar chart ────────────────────────────────────

# Per-share metrics. Tuple: (label, value_key, ratio_key)
# - value_key is the ratios_dict key for the per-share BRL value.
# - ratio_key is the ratios_dict key for the corresponding price multiple
#   (price / per-share value). When None, we compute price / value locally.
_PER_SHARE_ITEMS: list[tuple[str, str, str | None]] = [
    ("LPA",  "lpa",  "p_l"),     # price/LPA = P/L
    ("VPA",  "vpa",  "p_vpa"),   # price/VPA = P/VPA
    ("DPA",  "dpa",  None),      # price/DPA = (computed) — multiple, not yield
    ("RPA",  "rps",  "psr"),     # price/RPA = PSR
    ("RBPA", "rbpa", None),      # gross revenue / shares — NOT available yet
    ("CGPA", "cgpa", None),      # working_capital / shares
    ("DBPA", "dbpa", None),      # divida_bruta / shares
    ("APA",  "apa",  None),      # total_assets / shares — NOT available yet
    ("PPA",  "ppa",  None),      # total_liabilities / shares — NOT available yet
]


def _derive_per_share(ratios_dict: dict | None) -> dict[str, float | None]:
    """Compute per-share values NOT directly stored in ratios_dict.

    ratios_dict already has lpa (=eps), vpa (per-share VPA, restored), dpa
    (per-share DPA, restored), rps (per-share revenue). We derive the rest:
      - cgpa = working_capital / total_shares
      - dbpa = divida_bruta / total_shares
      - rbpa, apa, ppa = NOT derivable (no gross_revenue/total_assets/
        total_liabilities in ratios_dict) — return None.

    Returns {metric_key: value_or_None}.
    """
    if not isinstance(ratios_dict, dict):
        return {}

    shares = ratios_dict.get("total_shares")
    wc     = ratios_dict.get("working_capital")
    db     = ratios_dict.get("divida_bruta")

    return {
        "cgpa": _safe_div(wc, shares),
        "dbpa": _safe_div(db, shares),
        "rbpa": None,
        "apa":  None,
        "ppa":  None,
    }


def build_per_share_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Per-share tab sections: table + bar chart.

    Table columns: [Métrica, Valor (R$), Preço/Valor]
    The Preço/Valor column shows the price multiple (price / per-share value)
    where one is known (P/L for LPA, P/VPA for VPA, PSR for RPA); otherwise
    we compute it locally as price / per_share_value when both are present.
    """
    sections: list[dict] = []
    derived = _derive_per_share(ratios_dict)

    price = _safe_get(ratios_dict, "price")

    def _lookup(key: str) -> Any:
        v = _safe_get(ratios_dict, key)
        if v is None:
            v = derived.get(key)
        return v

    rows: list[list[str]] = []
    chart_labels: list[str] = []
    chart_data: list[float | None] = []

    for label, value_key, ratio_key in _PER_SHARE_ITEMS:
        value = _lookup(value_key)
        # Compute the price-multiple ratio.
        if ratio_key:
            ratio_value = _lookup(ratio_key)
        else:
            # Compute price / value locally.
            ratio_value = _safe_div(price, value)
        rows.append([label, _fmt(value, "brl_full"), _fmt(ratio_value, "num")])
        # Collect for chart (skip DPA — usually much smaller than LPA/VPA/RPA;
        # but include for completeness).
        chart_labels.append(label)
        chart_data.append(value)

    sections.append({
        "title": "Per-share Values (R$)",
        "type": "table",
        "columns": ["Métrica", "Valor (R$)", "Preço/Valor"],
        "rows": rows,
        "note": (
            "Per-share BRL values + the corresponding price multiple. "
            "RBPA / APA / PPA require engines not yet wired (see ROADMAP) — "
            "shown as '—'."
        ),
    })

    # ── Bar chart: per-share values side-by-side ──
    if any(v is not None for v in chart_data):
        sections.append({
            "type": "chart",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": chart_labels,
                    "datasets": [{
                        "label": "Per-share (R$)",
                        "data": [v if v is not None else 0 for v in chart_data],
                        "backgroundColor": "#3b82f6",
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "y": {"beginAtZero": True},
                    },
                    "plugins": {
                        "legend": {"display": False},
                    },
                },
            },
        })

    return sections


# ── Tab 4: Profitability -- ratio_grid ───────────────────────────────────────

_PROFITABILITY_ITEMS: list[tuple[str, str, str]] = [
    ("ROE",            "roe",              "pct"),
    ("ROA",            "roa",              "pct"),
    ("ROIC",           "roic",             "pct"),
    ("Gross Margin",   "gross_margin",     "pct"),
    ("Operating Margin","operating_margin","pct"),
    ("Net Margin",     "net_margin",       "pct"),
    ("EBITDA Margin",  "ebitda_margin",    "pct"),
    ("OCF Margin",     "ocf_margin",       "pct"),
    ("FCF Margin",     "fcf_margin",       "pct"),
]


def build_profitability_section(ratios_dict: dict | None) -> dict:
    """Build the Profitability tab as a single ratio_grid section."""
    items = [
        {
            "label": label,
            "value": _fmt(_safe_get(ratios_dict, key), spec),
        }
        for label, key, spec in _PROFITABILITY_ITEMS
    ]
    return {
        "title": "Profitability & Margins",
        "type": "ratio_grid",
        "categories": [
            {"label": "Profitability", "items": items},
        ],
    }


# ── Tab 5: Liquidity & Leverage -- ratio_grid + collapsible ──────────────────

_LIQUIDITY_ITEMS: list[tuple[str, str, str]] = [
    ("Current Ratio",    "current_ratio",    "num"),
    ("Quick Ratio",      "quick_ratio",      "num"),
    ("Cash Ratio",       "cash_ratio",       "num"),
    ("Working Capital",  "working_capital",  "brl"),
]

_LEVERAGE_ITEMS: list[tuple[str, str, str]] = [
    ("Debt/Equity",         "debt_equity",       "pct"),
    ("Net Debt/EBITDA",     "net_debt_ebitda",   "num"),
    ("Financial Leverage",  "financial_leverage","num"),
    ("Interest Coverage",   "interest_coverage", "num"),
    ("Cash Flow to Debt",   "cash_flow_to_debt", "pct"),
]

# Detailed leverage metrics (collapsible). DL = Dívida Líquida.
_DETAILED_LEVERAGE_ITEMS: list[tuple[str, str, str]] = [
    ("DL/EBIT",    "net_debt_ebit",    "num"),
    ("DL/EBITDA",  "net_debt_ebitda",  "num"),
    ("Gross Debt/Equity", "gross_debt_equity", "pct"),
]


def _derive_detailed_leverage(ratios_dict: dict | None) -> dict[str, float | None]:
    """Compute detailed leverage metrics from components in ratios_dict.

      - net_debt_ebit   = (divida_bruta - caixa) / ebit    [DL/EBIT]
      - gross_debt_equity = divida_bruta / patrimonio_liquido

    net_debt_ebitda is already in ratios_dict (from compute_all_ratios).
    """
    if not isinstance(ratios_dict, dict):
        return {}
    db  = ratios_dict.get("divida_bruta")
    cx  = ratios_dict.get("caixa")
    eb  = ratios_dict.get("ebit")
    pl  = ratios_dict.get("patrimonio_liquido")
    return {
        "net_debt_ebit":    _safe_div((db - cx) if (db is not None and cx is not None) else None, eb),
        "gross_debt_equity": _safe_div(db, pl),
    }


def build_liquidity_leverage_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Liquidity & Leverage tab sections.

    Returns 2 sections:
      1. ratio_grid with 2 categories: Liquidity + Leverage
      2. Collapsible "Detailed Leverage" with DL/EBIT, DL/EBITDA, Gross D/E
    """
    sections: list[dict] = []

    liquidity_items = [
        {"label": label, "value": _fmt(_safe_get(ratios_dict, key), spec)}
        for label, key, spec in _LIQUIDITY_ITEMS
    ]
    leverage_items = [
        {"label": label, "value": _fmt(_safe_get(ratios_dict, key), spec)}
        for label, key, spec in _LEVERAGE_ITEMS
    ]
    sections.append({
        "title": "Liquidity & Leverage",
        "type": "ratio_grid",
        "categories": [
            {"label": "Liquidity",  "items": liquidity_items},
            {"label": "Leverage",   "items": leverage_items},
        ],
    })

    # ── Collapsible: Detailed Leverage ──
    derived = _derive_detailed_leverage(ratios_dict)
    parts: list[str] = []
    for label, key, spec in _DETAILED_LEVERAGE_ITEMS:
        value = _safe_get(ratios_dict, key)
        if value is None:
            value = derived.get(key)
        parts.append(f"{label}: {_fmt(value, spec)}")
    sections.append({
        "type": "collapsible",
        "title": "Detailed Leverage",
        "text": " | ".join(parts),
        "open": False,
    })

    return sections


# ── Tab 6: Efficiency & Growth -- table + chart ──────────────────────────────

_EFFICIENCY_ITEMS: list[tuple[str, str, str]] = [
    ("Asset Turnover",        "asset_turnover",       "num"),
    ("Inventory Turnover",    "inventory_turnover",   "num"),
    ("Receivables Turnover",  "receivables_turnover", "num"),
    ("Fixed Asset Turnover",  "fixed_asset_turnover", "num"),
    ("CapEx/Revenue",         "capex_revenue",        "pct"),
]

# Growth metrics — these are NOT directly available in ratios_dict (they need
# historical periods). Listed here so the table can render '—' placeholders
# with a note that historical growth is on the ROADMAP.
_GROWTH_ITEMS: list[tuple[str, str]] = [
    ("Revenue Growth (3M)",      "revenue_growth_3m"),
    ("Revenue Growth (1Y)",      "revenue_growth_1y"),
    ("Revenue Growth (5Y)",      "revenue_growth_5y"),
    ("Gross Profit Growth (3M)", "gp_growth_3m"),
    ("Gross Profit Growth (1Y)", "gp_growth_1y"),
    ("Gross Profit Growth (5Y)", "gp_growth_5y"),
    ("Net Income Growth (3M)",   "ni_growth_3m"),
    ("Net Income Growth (1Y)",   "ni_growth_1y"),
    ("Net Income Growth (5Y)",   "ni_growth_5y"),
]

_GROWTH_CHART_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Receita Líquida",  [("3M", "revenue_growth_3m"),
                          ("1Y", "revenue_growth_1y"),
                          ("5Y", "revenue_growth_5y")]),
    ("Lucro Bruto",      [("3M", "gp_growth_3m"),
                          ("1Y", "gp_growth_1y"),
                          ("5Y", "gp_growth_5y")]),
    ("Lucro Líquido",    [("3M", "ni_growth_3m"),
                          ("1Y", "ni_growth_1y"),
                          ("5Y", "ni_growth_5y")]),
]

_GROWTH_CHART_COLORS = ["#22c55e", "#3b82f6", "#f59e0b"]


def build_efficiency_growth_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Efficiency & Growth tab sections: table + chart.

    Returns 2 sections:
      1. Table with 5 efficiency metrics + 9 growth cells (3M/1Y/5Y x 3 lines)
      2. Bar chart with 3M/1Y/5Y growth side-by-side for Revenue/GP/NI
         (skipped when no growth data is available — current state, on ROADMAP)
    """
    sections: list[dict] = []

    # ── Efficiency table ──
    eff_rows: list[list[str]] = [
        [label, _fmt(_safe_get(ratios_dict, key), spec)]
        for label, key, spec in _EFFICIENCY_ITEMS
    ]
    sections.append({
        "title": "Efficiency Ratios",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": eff_rows,
    })

    # ── Growth table (3M/1Y/5Y for Revenue / GP / NI) ──
    growth_rows: list[list[str]] = [
        [label, _fmt(_safe_get(ratios_dict, key), "pct")]
        for label, key in _GROWTH_ITEMS
    ]
    sections.append({
        "title": "Growth Metrics (3M / 1Y / 5Y)",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": growth_rows,
        "note": (
            "Historical growth metrics require annual/quarterly time series "
            "(on the ROADMAP). Currently '—' until historical engines are wired."
        ),
    })

    # ── Bar chart: 3M/1Y/5Y growth side-by-side for Revenue/GP/NI ──
    # Each label is a metric group; each dataset is a window (3M/1Y/5Y).
    chart_labels = [label for label, _ in _GROWTH_CHART_GROUPS]
    datasets: list[dict] = []
    for win_idx, win_label in enumerate(["3M", "1Y", "5Y"]):
        data: list[float | None] = []
        for _group_label, windows in _GROWTH_CHART_GROUPS:
            key = windows[win_idx][1]
            v = _safe_get(ratios_dict, key)
            # Convert fraction -> percentage for display (0.10 -> 10).
            data.append((v * 100) if v is not None else None)
        datasets.append({
            "label": win_label,
            "data": [v if v is not None else 0 for v in data],
            "backgroundColor": _GROWTH_CHART_COLORS[win_idx],
        })
    # Skip the chart entirely when ALL growth values are None (current state).
    has_any = any(
        _safe_get(ratios_dict, key) is not None
        for _label, windows in _GROWTH_CHART_GROUPS
        for _win_label, key in windows
    )
    if has_any:
        sections.append({
            "type": "chart",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": chart_labels,
                    "datasets": datasets,
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "y": {
                            "ticks": {},
                        },
                    },
                },
            },
        })

    return sections
