"""skills/cvm/financials/report/_helpers.py -- Shared utilities + constants
for the financials dashboard report builders.

This module is the single source of truth for:
  - Formatting helpers: ``_fmt`` (BRL/pct/num formatter via apply_fmt)
  - Numeric coercion:   ``_num_or_none``
  - Ratio scaling:      ``_pct_of`` (fraction → percentage)
  - Period utilities:   ``_period_sort_key`` (chronological sort key for
                        annual + quarterly period dicts),
                        ``_format_period_label`` (column-header labels)
  - Constants:          metric/ratio label maps, category lists, color maps
                        used by the Indicadores + Crescimento tabs.
  - Tooltip getter:     re-exported from ``skills.cvm._shared_report.tooltips``.

All other ``report/*.py`` submodules import from this module — never from
each other for these primitives (avoids circular imports).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt

# [v1.16.1] Shared builders extracted to skills/cvm/_shared_report/ so all
# CVM skills can reuse them. Financials re-exports them for backward
# compatibility with existing imports.
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


def _fmt(value: Any, spec: str) -> str:
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _num_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_of(value: Any) -> float | None:
    """Convert a fractional ratio (0.15) to a percentage number (15.0)."""
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


def _period_sort_key(p: dict) -> tuple:
    """[v2.1] Chronological sort key for period dicts.

    Uses (year, meses) from the period dict directly — CVM's `meses` field
    is always relative to the fiscal year (3=Q1, 6=Q2, 9=Q3, 12=Q4/annual),
    so it works for non-calendar filers too (unlike parsing calendar months).

    Falls back to data_fim_exerc string comparison (chronologically correct
    for all fiscal year types).
    """
    # [v2.1] Prefer (year, meses) — meses is fiscal-year-relative, not calendar
    year = p.get("year")
    meses = p.get("meses")
    if year is not None and meses is not None:
        return (int(year), int(meses))
    if year is not None:
        quarter = p.get("quarter")
        if quarter is not None:
            # Convert quarter to meses: Q1=3, Q2=6, Q3=9, Q4=12
            return (int(year), int(quarter) * 3 if int(quarter) > 0 else 0)
        return (int(year), 0)

    # Fallback: data_fim_exerc string sort (YYYY-MM-DD sorts chronologically)
    date_str = p.get("data_fim_exerc") or ""
    if date_str:
        return (0, 0, date_str)

    # Last resort: period label
    return (0, 0, str(p.get("period") or ""))


def _format_period_label(p: dict) -> str:
    """[v1.24] Format a period label for table column headers.

    Annual  → "2023"           (from ``period`` or ``data_fim_exerc`` "2023-12-31")
    Quarterly → "2T2026"       (from ``period`` or ``data_fim_exerc`` "2026-06-30")

    Falls back to the raw date string when the month isn't a standard
    quarter-end (3/6/9/12) — graceful degradation for non-calendar filers.
    """
    if p.get("period"):
        return str(p["period"])
    date = p.get("data_fim_exerc") or ""
    if not date:
        return "—"
    try:
        year = date[:4]
        month = int(date[5:7])
    except (ValueError, IndexError):
        return date
    if month == 12:
        return year  # annual
    quarter_map = {3: "1T", 6: "2T", 9: "3T", 12: "4T"}
    q_label = quarter_map.get(month)
    if q_label:
        return f"{q_label}{year}"
    return date


# ── Constants ────────────────────────────────────────────────────────────────

# Pretty labels for individual metric names (registry canonical names).
# Only the most common ones — anything not in here falls back to the canonical
# name as the label.
_METRIC_LABELS = {
    # profitability
    "roe": "ROE", "roa": "ROA", "roic": "ROIC",
    "gross_margin": "Marg. Bruta", "operating_margin": "Marg. Operacional",
    "net_margin": "Marg. Líquida", "ebitda_margin": "Marg. EBITDA",
    "ocf_margin": "Marg. FCO", "fcf_margin": "Marg. FCF",
    # liquidity
    "current_ratio": "Liquidez Corrente", "quick_ratio": "Liquidez Seca",
    "cash_ratio": "Liquidez Imediata", "working_capital": "Capital de Giro",
    # leverage
    "debt_equity": "Dívida/PL", "net_debt_ebitda": "Dív. Líq/EBITDA",
    "dl_ebit": "Dív. Líq/EBIT",
    "interest_coverage": "Cobertura Juros", "cash_flow_to_debt": "FCO/Dívida",
    # efficiency
    "asset_turnover": "Giro do Ativo",
    "inventory_turnover": "Giro Estoque",
    "receivables_turnover": "Giro Contas a Receber",
    "fixed_asset_turnover": "Giro Imobilizado",
    "capex_revenue": "Capex/Receita",
    # growth
    "retention_ratio": "Taxa de Retenção",
    "sustainable_growth": "Crescimento Sustentável",
    # valuation
    "ev_ebitda": "EV/EBITDA", "ev_ebit": "EV/EBIT",
    "ev_fcf": "EV/FCF", "ev_sales": "EV/Sales",
    "p_ebit": "P/EBIT", "p_fcf": "P/FCF", "p_fco": "P/FCO",
    "graham_number": "Graham Number",
    "price_to_tangible_book": "P/VPA Tangível",
    # per_share (registry returns the price ratio, not the per-share value)
    "lpa": "P/L", "vpa": "P/VPA", "dpa": "Div Yield", "rps": "PSR",
    # tax
    "effective_tax_rate": "Taxa de Tributo Efetiva",
}

# Metrics whose values are ratios (display as pct); everything else num.
_RATIO_PCT_KEYS = {
    "roe", "roa", "roic", "roi", "gross_margin", "operating_margin", "net_margin",
    "ebitda_margin", "ocf_margin", "fcf_margin",
    "debt_equity", "cash_flow_to_debt", "capex_revenue",
    "retention_ratio", "sustainable_growth",
    "dpa", "effective_tax_rate",
    # [v1.25] Growth + CAGR metrics (all fractions displayed as %).
    # Previously shown as raw 0.15 — fixed to 15%.
    "revenue_growth_3m", "revenue_growth_1y", "revenue_growth_5y",
    "net_income_growth_3m", "net_income_growth_1y", "net_income_growth_5y",
    "gross_profit_growth_3m", "gross_profit_growth_1y", "gross_profit_growth_5y",
    "revenue_cagr_3m", "revenue_cagr_1y", "revenue_cagr_5y",
    "earnings_cagr_3m", "earnings_cagr_1y", "earnings_cagr_5y",
    "gross_profit_cagr_3m", "gross_profit_cagr_1y", "gross_profit_cagr_5y",
    # [v1.25] Valuation fractions (displayed as %).
    "dcf_margin_of_safety", "earnings_yield", "irr", "wacc",
}

# [new commit] Metrics to EXCLUDE from the Indicadores tab — these are raw
# BRL numbers (not ratios), so showing them alongside ratios is misleading.
# "working_capital" = Ativo Circulante - Passivo Circulante (R$), not a %.
# User feedback: "remove Capital de Giro from Liquidez — it's raw number,
# not ratio, metric, etc".
_INDICADORES_EXCLUDE = {"working_capital"}

# Ratio-grid category labels (registry category -> pretty PT-BR label).
_RATIO_CATEGORY_LABELS = {
    "profitability": "Rentabilidade",
    "liquidity":     "Liquidez",
    "leverage":      "Endividamento",
    "efficiency":    "Eficiência",
    "growth":        "Crescimento",
    "tax":           "Tributos",
    "valuation":     "Valuation",
    "per_share":     "Por Ação",
}

# Categories shown in the Indicadores tab (order matters for display).
# [v1.25] "growth" removed — moved to the dedicated Crescimento tab
# (build_crescimento_sections now emits a growth ratio_grid at the top).
_INDICADORES_CATEGORIES = [
    "valuation", "profitability", "liquidity",
    "leverage", "efficiency", "tax",
]

# [v1.25] Valuation metrics EXCLUDED from charts (kept in ratio_grid).
# These are BRL values (not ratios) — including them on a chart with
# ratio multiples breaks the y-axis scale.
# - dcf_intrinsic_value: R$ per share (~tens of R$)
# - graham_number:       R$ per share (~tens of R$)
_VALUATION_CHART_EXCLUDE = {"dcf_intrinsic_value", "graham_number"}

# [v1.25] Distinct colors per ratio_grid box group, used in the per-group
# bar charts. Picked so adjacent groups have contrasting hues.
_GROUP_CHART_COLORS = {
    # valuation
    "EV (Enterprise Value)": "#0d9488",  # teal
    "P/ (Price)":            "#2563eb",  # blue
    "Indicadores de Valor":  "#7c3aed",  # purple
    # profitability
    "Retorno":               "#16a34a",  # green
    "Margens":               "#ea580c",  # orange
    "Rentabilidade":         "#16a34a",  # green (else bucket — DuPont)
    # efficiency
    "Giro":                  "#db2777",  # pink
    "Eficiência":            "#db2777",  # pink (else bucket — Capex)
    # liquidity
    "Liquidez":              "#0891b2",  # cyan
    # leverage
    "Ratios":                "#0891b2",  # cyan
    "Multiples/Coverage":    "#dc2626",  # red
    "Endividamento":         "#dc2626",  # red (fallback if not split)
    # tax
    "Tributos":              "#ca8a04",  # yellow
    # growth
    "Receita":               "#0d9488",  # teal
    "Lucro Líquido":         "#2563eb",  # blue
    "Resultado Bruto":       "#7c3aed",  # purple
    "Outros Crescimento":    "#64748b",  # slate
    "Crescimento":           "#64748b",  # slate (else bucket)
    "Outros":                "#64748b",  # slate
}

# [v1.25] Descriptive chart titles for the 3 valuation groups (the user
# explicitly named them in the v1.25 spec).
_VALUATION_CHART_TITLES = {
    "EV (Enterprise Value)": "EV — Múltiplos Enterprise Value",
    "P/ (Price)":            "P/ — Múltiplos de Preço",
    "Indicadores de Valor":  "Indicadores de Valor",
}

# [v1.25] Descriptive chart descriptions for valuation groups.
_VALUATION_CHART_DESCRIPTIONS = {
    "EV (Enterprise Value)": (
        "Múltiplos de Enterprise Value: EV/EBIT, EV/EBITDA, EV/FCF e "
        "EV/Sales. Quanto o EV vale relativo aos geradores de caixa da "
        "empresa."
    ),
    "P/ (Price)": (
        "Múltiplos de Preço: P/EBIT, P/EBITDA, P/EV, P/FCF, P/FCO e "
        "P/VPA Tangível. Quanto o mercado paga por R$1 de cada base."
    ),
    "Indicadores de Valor": (
        "Indicadores de valor: DCF Margem de Segurança, Earnings Yield, "
        "TIR (IRR), Magic Number e WACC. Métricas compostas que combinam "
        "preço, valor intrínseco e retorno."
    ),
}
