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

# [v1.8] Shared tooltip system — import from _shared_report so all CVM
# skills use the same PT-BR formula strings.
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


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
    """Build the Overview tab sections: split metrics into 3 related tables.

    [v1.8] Removed Price Details collapsible (price info is in the company
    header now). Split the single Key Metrics table into 3 grouped tables:
      1. Métricas de Mercado (market-cap-based: P/L, P/VPA, EV/EBITDA, etc.)
      2. Resultado (income statement: Receita, EBITDA, Lucro Líquido, etc.)
      3. Balanço (balance sheet: Ativo Total, PL, Dívida, Caixa)
    """
    sections: list[dict] = []

    # ── Table 1: Métricas de Mercado ──
    _MERCADO_ITEMS = [
        ("Market Cap",         "market_cap",         "brl", ""),
        ("EV",                 "ev",                 "brl", "Enterprise Value = Market Cap + Dívida Líquida"),
        ("P/L",                "p_l",                "num", _get_tooltip("lpa")),
        ("P/VPA",              "p_vpa",              "num", _get_tooltip("vpa")),
        ("EV/EBITDA",          "ev_ebitda",          "num", _get_tooltip("ev_ebitda")),
        ("Dividend Yield",     "dividend_yield",     "pct", _get_tooltip("dpa")),
        ("PSR",                "psr",                "num", _get_tooltip("rps")),
        ("DPA (TTM)",          "dpa",                "brl_full", "Dividendos por Ação = Dividendos pagos / total de ações"),
    ]
    sections.append({
        "title": "Métricas de Mercado",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [
            [{"text": label, "tooltip": tooltip}, _fmt(_safe_get(ratios_dict, key), spec)]
            for label, key, spec, tooltip in _MERCADO_ITEMS
        ],
    })

    # ── Table 2: Resultado ──
    _RESULTADO_ITEMS = [
        ("Receita Líquida",    "receita_liquida",    "brl", "Receita total após deduções (DRE 3.01)"),
        ("EBITDA",             "ebitda",             "brl", "EBIT + D&A (Depreciação e Amortização)"),
        ("Lucro Líquido",      "lucro_liquido",      "brl", "Lucro/Prejuízo Consolidado (DRE 3.11)"),
        ("ROE",                "roe",                "pct", _get_tooltip("roe")),
        ("ROA",                "roa",                "pct", _get_tooltip("roa")),
        ("ROIC",               "roic",               "pct", _get_tooltip("roic")),
    ]
    sections.append({
        "title": "Resultado (TTM)",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [
            [{"text": label, "tooltip": tooltip}, _fmt(_safe_get(ratios_dict, key), spec)]
            for label, key, spec, tooltip in _RESULTADO_ITEMS
        ],
    })

    # ── Table 3: Balanço ──
    _BALANCO_ITEMS = [
        ("Patrimônio Líquido", "patrimonio_liquido", "brl", "Capital próprio dos acionistas (BPP 2.03)"),
        ("Dívida Bruta",       "divida_bruta",       "brl", "Empréstimos Circ + Não Circ (2.01.04 + 2.02.01)"),
        ("Caixa",              "caixa",              "brl", "Caixa e Equivalentes (BPA 1.01.01)"),
        ("Total de Ações",     "total_shares",       "int", "Total de ações outstanding (FRE)"),
    ]
    sections.append({
        "title": "Balanço Patrimonial",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [
            [{"text": label, "tooltip": tooltip}, _fmt(_safe_get(ratios_dict, key), spec)]
            for label, key, spec, tooltip in _BALANCO_ITEMS
        ],
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
    """Build the Multiples tab sections — split by group.

    [v1.8] Split the single top-10 table into 3 grouped tables:
      1. Múltiplos de Preço (P/L, P/VPA, P/EBIT, P/EBITDA, PSR, P/FCO, P/FCF)
      2. Múltiplos EV (EV/EBIT, EV/EBITDA, EV/Sales, EV/FCF, P/EV)
      3. Menos Comuns (P/Ativos, P/Passivos, P/RB, P/CG, P/DB, P/Tangible Book)
    Each group has its own bar chart. Less Common is now a table (was collapsible).
    """
    sections: list[dict] = []
    derived = _derive_multiples(ratios_dict)

    def _lookup(key: str) -> Any:
        v = _safe_get(ratios_dict, key)
        if v is None:
            v = derived.get(key)
        return v

    # ── Group 1: Múltiplos de Preço ──
    _PRICE_MULTIPLES = [
        ("P/L",       "p_l",       "num", "Cheap if < 10; expensive if > 25",  _get_tooltip("lpa")),
        ("P/VPA",     "p_vpa",     "num", "Cheap if < 1; expensive if > 3",    _get_tooltip("vpa")),
        ("P/EBIT",    "p_ebit",    "num", "Cheap if < 8; expensive if > 20",   _get_tooltip("p_ebit")),
        ("P/EBITDA",  "p_ebitda",  "num", "Cheap if < 8; expensive if > 15",   _get_tooltip("p_ebitda")),
        ("PSR",       "psr",       "num", "Cheap if < 1; expensive if > 3",    _get_tooltip("rps")),
        ("P/FCO",     "p_fco",     "num", "Cheap if < 10; expensive if > 25",  _get_tooltip("p_fco")),
        ("P/FCF",     "p_fcf",     "num", "Cheap if < 15; expensive if > 30",  _get_tooltip("p_fcf")),
    ]
    price_rows = []
    price_chart_labels = []
    price_chart_values = []
    for label, key, spec, interp, formula in _PRICE_MULTIPLES:
        value = _lookup(key)
        price_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
        if value is not None:
            price_chart_labels.append(label)
            price_chart_values.append(float(value))
    sections.append({
        "title": "Múltiplos de Preço",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": price_rows,
    })
    if len(price_chart_labels) >= 2:
        sections.append({
            "type": "chart",
            "title": "Múltiplos de Preço — Comparativo",
            "description": "P/L, P/VPA, P/EBIT, P/EBITDA, PSR. Menor = mais barato.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": price_chart_labels,
                    "datasets": [{"label": "Preço", "data": price_chart_values,
                                  "backgroundColor": "#3b82f6"}],
                },
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # ── Group 2: Múltiplos EV ──
    _EV_MULTIPLES = [
        ("EV/EBIT",   "ev_ebit",   "num", "Cheap if < 8; expensive if > 15", _get_tooltip("ev_ebit")),
        ("EV/EBITDA", "ev_ebitda", "num", "Cheap if < 8; expensive if > 15", _get_tooltip("ev_ebitda")),
        ("EV/Sales",  "ev_sales",  "num", "Cheap if < 1; expensive if > 3",   _get_tooltip("ev_sales")),
        ("EV/FCF",    "ev_fcf",    "num", "Cheap if < 10; expensive if > 25", _get_tooltip("ev_fcf")),
        ("P/EV",      "p_ev",      "num", "Cheap if < 1; expensive if > 3",   _get_tooltip("p_ev")),
    ]
    ev_rows = []
    ev_chart_labels = []
    ev_chart_values = []
    for label, key, spec, interp, formula in _EV_MULTIPLES:
        value = _lookup(key)
        ev_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
        if value is not None:
            ev_chart_labels.append(label)
            ev_chart_values.append(float(value))
    sections.append({
        "title": "Múltiplos EV (Enterprise Value)",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": ev_rows,
    })
    if len(ev_chart_labels) >= 2:
        sections.append({
            "type": "chart",
            "title": "Múltiplos EV — Comparativo",
            "description": "EV/EBIT, EV/EBITDA, EV/Sales, EV/FCF. Menor = mais barato.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": ev_chart_labels,
                    "datasets": [{"label": "EV", "data": ev_chart_values,
                                  "backgroundColor": "#f59e0b"}],
                },
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # ── Group 3: Menos Comuns (table, was collapsible) ──
    less_rows = []
    for label, key, spec, interp in _MULTIPLES_LESS_COMMON:
        value = _lookup(key)
        formula = _get_tooltip(key) or _get_tooltip(key.replace("_", ""))
        less_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
    sections.append({
        "title": "Múltiplos Menos Comuns",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": less_rows,
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
        # [v1.8] Add tooltip/formula column.
        formula = _get_tooltip(value_key) or f"{label} = valor total / total de ações"
        rows.append([{"text": label, "tooltip": formula}, _fmt(value, "brl_full"), _fmt(ratio_value, "num")])
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
            "title": "Valores por Ação — Comparativo",
            "description": "LPA, VPA, DPA, RPS e derivados. Mostra o valor por ação de cada métrica.",
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


def build_profitability_section(ratios_dict: dict | None) -> dict | list:
    """Build the Profitability tab — ratio_grid + split charts.

    [v1.8] Split the single bar chart into 2: Returns (ROE/ROA/ROIC) +
    Margins (Gross/Operating/Net/EBITDA/OCF/FCF).
    """
    items = []
    for label, key, spec in _PROFITABILITY_ITEMS:
        raw = _safe_get(ratios_dict, key)
        items.append({
            "label": label,
            "value": _fmt(raw, spec),
            "value_raw": float(raw) if raw is not None else None,
            "tooltip": _get_tooltip(key),
        })
    # Split items into Returns (first 3) + Margins (last 6).
    returns_items = items[:3]
    margins_items = items[3:]
    sections: list[dict] = [{
        "title": "Profitability & Margins",
        "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
        "type": "ratio_grid",
        "categories": [
            {"label": "Retornos", "items": returns_items},
            {"label": "Margens",  "items": margins_items},
        ],
    }]
    # [v1.8] Chart 1: Returns (ROE/ROA/ROIC)
    ret_labels = [i["label"] for i in returns_items if i.get("value_raw") is not None]
    ret_values = [i["value_raw"] for i in returns_items if i.get("value_raw") is not None]
    if len(ret_labels) >= 2:
        # Convert to percentage for display
        ret_pct = [v * 100 if abs(v) < 1 else v for v in ret_values]
        sections.append({
            "type": "chart",
            "title": "Retornos — ROE / ROA / ROIC",
            "description": "Comparativo dos retornos. Maior = melhor.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": ret_labels,
                         "datasets": [{"label": "Retornos (%)", "data": ret_pct,
                                       "backgroundColor": "#0d9488"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })
    # [v1.8] Chart 2: Margins
    mar_labels = [i["label"] for i in margins_items if i.get("value_raw") is not None]
    mar_values = [i["value_raw"] for i in margins_items if i.get("value_raw") is not None]
    if len(mar_labels) >= 2:
        mar_pct = [v * 100 if abs(v) < 1 else v for v in mar_values]
        sections.append({
            "type": "chart",
            "title": "Margens — Bruta / EBIT / EBITDA / Líquida / FCO / FCF",
            "description": "Comparativo das margens operacionais. Maior = melhor.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": mar_labels,
                         "datasets": [{"label": "Margens (%)", "data": mar_pct,
                                       "backgroundColor": "#f59e0b"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })
    if len(sections) == 1:
        return sections[0]
    return sections


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
    """Build the Liquidity & Leverage tab — ratio_grid + charts + detailed table.

    [v1.8] Replaced the collapsible with a proper table. Added 2 bar charts:
    Liquidity ratios + Leverage ratios.
    """
    sections: list[dict] = []

    liquidity_items = []
    for label, key, spec in _LIQUIDITY_ITEMS:
        raw = _safe_get(ratios_dict, key)
        liquidity_items.append({
            "label": label,
            "value": _fmt(raw, spec),
            "value_raw": float(raw) if raw is not None else None,
            "tooltip": _get_tooltip(key),
        })
    leverage_items = []
    for label, key, spec in _LEVERAGE_ITEMS:
        raw = _safe_get(ratios_dict, key)
        leverage_items.append({
            "label": label,
            "value": _fmt(raw, spec),
            "value_raw": float(raw) if raw is not None else None,
            "tooltip": _get_tooltip(key),
        })
    sections.append({
        "title": "Liquidity & Leverage",
        "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
        "type": "ratio_grid",
        "categories": [
            {"label": "Liquidity",  "items": liquidity_items},
            {"label": "Leverage",   "items": leverage_items},
        ],
    })

    # [v1.8] Chart 1: Liquidity ratios
    liq_labels = [i["label"] for i in liquidity_items if i.get("value_raw") is not None]
    liq_values = [i["value_raw"] for i in liquidity_items if i.get("value_raw") is not None]
    if len(liq_labels) >= 2:
        sections.append({
            "type": "chart",
            "title": "Liquidez — Comparativo",
            "description": "Liquidez Corrente, Seca, Imediata + Capital de Giro.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": liq_labels,
                         "datasets": [{"label": "Liquidez", "data": liq_values,
                                       "backgroundColor": "#3b82f6"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # [v1.8] Chart 2: Leverage ratios
    lev_labels = [i["label"] for i in leverage_items if i.get("value_raw") is not None]
    lev_values = [i["value_raw"] for i in leverage_items if i.get("value_raw") is not None]
    if len(lev_labels) >= 2:
        lev_pct = [v * 100 if abs(v) < 1 else v for v in lev_values]
        sections.append({
            "type": "chart",
            "title": "Alavancagem — Comparativo",
            "description": "Dívida/PL, Dív.Líq/EBITDA, Alavancagem Financeira, Cobertura Juros, FCO/Dívida.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": lev_labels,
                         "datasets": [{"label": "Alavancagem", "data": lev_pct,
                                       "backgroundColor": "#ef4444"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # [v1.8] Detailed Leverage — table (was collapsible).
    derived = _derive_detailed_leverage(ratios_dict)
    detail_rows = []
    for label, key, spec in _DETAILED_LEVERAGE_ITEMS:
        value = _safe_get(ratios_dict, key)
        if value is None:
            value = derived.get(key)
        interp = ""
        if key == "net_debt_ebit" and value is not None:
            interp = "Baixa alavancagem" if value < 2 else "Alta alavancagem" if value > 4 else "Alavancagem moderada"
        elif key == "net_debt_ebitda" and value is not None:
            interp = "Baixa" if value < 2 else "Alta" if value > 3 else "Moderada"
        elif key == "gross_debt_equity" and value is not None:
            interp = "Baixa" if value < 0.3 else "Alta" if value > 0.6 else "Moderada"
        formula = _get_tooltip(key) or _get_tooltip("dl_ebit" if key == "net_debt_ebit" else key)
        if not formula:
            formula = f"{label} = (Dívida Bruta - Caixa) / EBIT" if "ebit" in key and "ebitda" not in key else f"{label} = Dívida Bruta / PL"
        detail_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
    sections.append({
        "title": "Alavancagem Detalhada",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": detail_rows,
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
    ("Gross Profit Growth (3M)", "gross_profit_growth_3m"),
    ("Gross Profit Growth (1Y)", "gross_profit_growth_1y"),
    ("Gross Profit Growth (5Y)", "gross_profit_growth_5y"),
    ("Net Income Growth (3M)",   "net_income_growth_3m"),
    ("Net Income Growth (1Y)",   "net_income_growth_1y"),
    ("Net Income Growth (5Y)",   "net_income_growth_5y"),
]

_GROWTH_CHART_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Receita Líquida",  [("3M", "revenue_growth_3m"),
                          ("1Y", "revenue_growth_1y"),
                          ("5Y", "revenue_growth_5y")]),
    ("Lucro Bruto",      [("3M", "gross_profit_growth_3m"),
                          ("1Y", "gross_profit_growth_1y"),
                          ("5Y", "gross_profit_growth_5y")]),
    ("Lucro Líquido",    [("3M", "net_income_growth_3m"),
                          ("1Y", "net_income_growth_1y"),
                          ("5Y", "net_income_growth_5y")]),
]

_GROWTH_CHART_COLORS = ["#22c55e", "#3b82f6", "#f59e0b"]


def build_efficiency_growth_sections(
    ratios_dict: dict | None,
    annual_periods: list[dict] | None = None,
) -> list[dict]:
    """Build the Efficiency & Growth tab — split growth by metric + charts.

    [v1.8] Split the single Growth Metrics table into 3 per-metric tables
    (Receita, Lucro Bruto, Lucro Líquido) each with 3M/1Y/5Y. Added per-metric
    bar charts. Fixed growth values: if ratios_dict growth keys are None,
    compute growth from annual_periods (fetched from financials) as fallback.
    """
    sections: list[dict] = []

    # ── Efficiency table ──
    # [v1.8] Added tooltips + value_raw for consistency with other tabs.
    eff_rows: list[list[str]] = []
    for label, key, spec in _EFFICIENCY_ITEMS:
        raw = _safe_get(ratios_dict, key)
        eff_rows.append([
            {"text": label, "tooltip": _get_tooltip(key)},
            _fmt(raw, spec),
        ])
    sections.append({
        "title": "Efficiency Ratios",
        "description": "Giro do Ativo, Giro de Estoque, Giro de Contas a Receber, etc. Passe o mouse sobre a métrica para ver a fórmula (ⓘ).",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": eff_rows,
    })

    # ── Growth: compute from annual_periods if ratios_dict growth is None ──
    # [v1.8] This fixes the "all —" bug. The calculations growth metrics
    # may return None when historical engines lack data. Fall back to
    # computing growth directly from annual_periods (from financials).
    def _get_growth(key: str, annual_key: str, lookback_years: int) -> float | None:
        """Get growth from ratios_dict first, fall back to annual_periods."""
        val = _safe_get(ratios_dict, key)
        if val is not None:
            return val
        # Fallback: compute from annual_periods
        if not annual_periods or len(annual_periods) < 2:
            return None
        try:
            from skills.cvm.calculations.growth_helpers import (
                growth_at, LOOKBACK_1Y, LOOKBACK_5Y,
            )
            # Build period list for growth_at
            metric_map = {
                "revenue": "receita_liquida",
                "gross_profit": "lucro_bruto",
                "net_income": "lucro_liquido",
            }
            metric_name = annual_key
            periods = []
            for p in annual_periods:
                if not p.get("period"):
                    continue
                val = (p.get("metrics") or {}).get(metric_name)
                if val is not None:
                    d = p.get("data_fim_exerc") or f"{p['period']}-12-31"
                    periods.append({"date": str(d)[:10], "value": float(val)})
            periods.sort(key=lambda x: x["date"])
            if len(periods) < 2:
                return None
            target_date = periods[-1]["date"]
            lookback = LOOKBACK_1Y if lookback_years == 1 else LOOKBACK_5Y
            return growth_at(periods, target_date, lookback)
        except Exception:
            return None

    # [v4] Regrouped by TIME HORIZON (was by metric type). User feedback:
    # "instead of sorting by type, lets sort and group by time, to compare
    # each type by 3m/1y/5y". So now: "Crescimento 3M" table shows all 3
    # metrics, "Crescimento 1Y" shows all 3, "Crescimento 5Y" shows all 3.
    _GROWTH_METRICS = [
        ("Receita Líquida", "revenue_growth_3m", "revenue_growth_1y", "revenue_growth_5y", "receita_liquida"),
        ("Lucro Bruto", "gross_profit_growth_3m", "gross_profit_growth_1y", "gross_profit_growth_5y", "lucro_bruto"),
        ("Lucro Líquido", "net_income_growth_3m", "net_income_growth_1y", "net_income_growth_5y", "lucro_liquido"),
    ]
    _HORIZONS = [("3M", 0), ("1Y", 1), ("5Y", 5)]
    for win_label, lookback_years in _HORIZONS:
        rows = []
        chart_labels = []
        chart_values = []
        for metric_label, key_3m, key_1y, key_5y, annual_key in _GROWTH_METRICS:
            key = key_3m if win_label == "3M" else key_1y if win_label == "1Y" else key_5y
            val = _get_growth(key, annual_key, lookback_years)
            formula = _get_tooltip(key)
            if not formula:
                formula = f"Crescimento de {metric_label} {win_label} = (atual - anterior) / |anterior|"
            rows.append([{"text": metric_label, "tooltip": formula}, _fmt(val, "pct")])
            if val is not None:
                chart_labels.append(metric_label)
                chart_values.append(val * 100 if abs(val) < 1 else val)
        sections.append({
            "title": f"Crescimento {win_label}",
            "description": f"Comparativo de crescimento {win_label} entre Receita, Lucro Bruto e Lucro Líquido.",
            "type": "table",
            "columns": ["Métrica", "Crescimento"],
            "rows": rows,
        })
        if len(chart_labels) >= 2:
            _HORIZON_COLORS = {"3M": "#a855f7", "1Y": "#22c55e", "5Y": "#3b82f6"}
            sections.append({
                "type": "chart",
                "title": f"Crescimento {win_label} — Comparativo",
                "description": f"Crescimento {win_label} de Receita Líquida, Lucro Bruto e Lucro Líquido.",
                "chart_data": {
                    "type": "bar",
                    "data": {"labels": chart_labels,
                             "datasets": [{"label": f"Crescimento {win_label}", "data": chart_values,
                                           "backgroundColor": _HORIZON_COLORS.get(win_label, "#0d9488")}]},
                    "options": {"responsive": True, "maintainAspectRatio": False,
                                "scales": {"y": {"beginAtZero": True}}},
                },
            })

    return sections
