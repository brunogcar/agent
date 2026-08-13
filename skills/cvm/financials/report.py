"""skills/cvm/financials/report.py -- Dashboard composition helpers.

[v1.12] Reorganized for the 7-tab dashboard (Overview / Indicadores /
Crescimento / Balanço / DRE / DFC / DVA). Each builder returns a section
shaped for the dashboard template:

  {"type": "table",      "title": ..., "columns": [...], "rows": [...]}
  {"type": "ratio_grid", "title": ..., "categories": [{label, items}]}
  {"type": "chart",      "chart_data": {type, data, options}}
  {"type": "subtabs",    "tabs": [{name, sections}]}
  {"type": "collapsible","title": ..., "text": ..., "open": False}
  {"type": "two_column", "left_title": ..., "left_rows": ..., ...}
  {"type": "text",       "text": ...}

KPIs (top-level) are produced separately and placed at the top level of
the dashboard payload (`result["kpis"]`).

The dashboard mode calls the standalone statement modes (bpa/bpp/dre/dfc/
dva) to fetch raw account data — this module only shapes their output
into dashboard sections. Each statement-mode call is wrapped in try/except
by the dashboard so a failure in one statement degrades the corresponding
tab to an error table instead of crashing the whole dashboard.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt

# [v1.16.1] Shared builders extracted to skills/cvm/_shared_report/ so all
# CVM skills can reuse them. Financials re-exports them for backward
# compatibility with existing imports.
from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


def _fmt(value: Any, spec: str) -> str:
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def annual_metric(latest_annual_period: dict | None, name: str) -> float | None:
    if not latest_annual_period:
        return None
    return (latest_annual_period.get("metrics") or {}).get(name)


def annual_ratio(latest_annual_period: dict | None, name: str) -> float | None:
    if not latest_annual_period:
        return None
    return (latest_annual_period.get("ratios") or {}).get(name)



# ── KPI cards (top-level) ────────────────────────────────────────────────────

def build_overview_kpis(
    latest_annual_period: dict | None,
    roe_val: float | None,
    roic_val: float | None,
    net_debt_ebitda_val: float | None,
    ttm_result: dict | None = None,
) -> list[dict]:
    """Build 6 KPI cards with pre-formatted values.

    [new commit] F9 fix: "Receita (TTM)" now shows ACTUAL TTM data (from
    ttm_result), not the annual DFP value. Was calling annual_metric() which
    returns the latest annual period — only equals TTM on Dec 31. Now
    prefers ttm_result["periods"][-1]["metrics"] with annual fallback for
    new filers (<4 quarters of ITR history).
    """
    # [new commit] Extract TTM metrics if available, fall back to annual.
    ttm_metrics: dict = {}
    if ttm_result and isinstance(ttm_result, dict) and ttm_result.get("status") == "ok":
        ttm_periods = ttm_result.get("periods") or []
        if ttm_periods:
            ttm_metrics = ttm_periods[0].get("metrics") or {}

    # Receita: prefer TTM, fall back to annual
    receita_val = ttm_metrics.get("receita_liquida")
    if receita_val is None:
        receita_val = annual_metric(latest_annual_period, "receita_liquida")
    # EBITDA: prefer TTM, fall back to annual
    ebitda_val = ttm_metrics.get("ebitda")
    if ebitda_val is None:
        ebitda_val = annual_metric(latest_annual_period, "ebitda")
    # Lucro Líquido: prefer TTM, fall back to annual
    lucro_val = ttm_metrics.get("lucro_liquido")
    if lucro_val is None:
        lucro_val = annual_metric(latest_annual_period, "lucro_liquido")

    return [
        {
            "label": "Receita (TTM)",
            "value": _fmt(receita_val, "brl"),
            "unit": "BRL",
        },
        {
            "label": "EBITDA (TTM)",
            "value": _fmt(ebitda_val, "brl"),
            "unit": "BRL",
        },
        {
            "label": "Lucro Líquido (TTM)",
            "value": _fmt(lucro_val, "brl"),
            "unit": "BRL",
        },
        {
            "label": "ROE",
            "value": _fmt(roe_val, "pct"),
            "unit": "ratio",
        },
        {
            "label": "ROIC",
            "value": _fmt(roic_val, "pct"),
            "unit": "ratio",
        },
        {
            "label": "Dívida Líquida/EBITDA",
            "value": _fmt(net_debt_ebitda_val, "num"),
            "unit": "x",
        },
    ]


# ── Tab 1: Overview ──────────────────────────────────────────────────────────

def build_overview_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
    ratios_payload: dict,
) -> list[dict]:
    """Build Overview tab: latest-annual summary table + quarterly trend +
    optional freshness table. Carries a short summary text at the top.
    """
    sections: list[dict] = []

    summary_lines: list[str] = []
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        summary_lines.append(
            f"Período mais recente: {latest_annual_period.get('period', '—')}."
        )
        summary_lines.append(
            f"Receita Líquida: {_fmt(m.get('receita_liquida'), 'brl')}. "
            f"EBITDA: {_fmt(m.get('ebitda'), 'brl')} "
            f"(método {m.get('ebitda_method', '—')}). "
            f"Lucro Líquido: {_fmt(m.get('lucro_liquido'), 'brl')}."
        )
    else:
        summary_lines.append("Dados anuais indisponíveis para esta empresa.")
    if ratios_payload.get("roe") is not None or ratios_payload.get("roic") is not None:
        summary_lines.append(
            f"ROE: {_fmt(ratios_payload.get('roe'), 'pct')} • "
            f"ROIC: {_fmt(ratios_payload.get('roic'), 'pct')} • "
            f"Dív.Líq/EBITDA: {_fmt(ratios_payload.get('net_debt_ebitda'), 'num')}."
        )
    sections.append({
        "type": "text",
        "text": " ".join(summary_lines),
    })

    # Latest-annual headline metrics table
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        r = latest_annual_period.get("ratios") or {}
        # [v1.25] Tooltips now on the FIRST column (metric name/label),
        # not the value cell. User feedback: "tooltips should be on the
        # metric name (e.g. 'Receita Líquida'), not on the value".
        def _label(text: str, tooltip: str) -> dict:
            return {"text": text, "tooltip": tooltip}

        rows = [
            ["Período",           latest_annual_period.get("period", "—")],
            [_label("Receita Líquida",
                    "Receita Líquida = DRE 3.01 (Receita de Vendas)"),
                                  _fmt(m.get("receita_liquida"),   "brl")],
            [_label("Lucro Bruto",
                    "Lucro Bruto = DRE 3.02 (Receita - CPV)"),
                                  _fmt(m.get("lucro_bruto"),       "brl")],
            [_label("EBIT",
                    "EBIT = DRE 3.05 (Resultado antes de juros e impostos)"),
                                  _fmt(m.get("ebit"),              "brl")],
            [_label("EBITDA",
                    "EBITDA = EBIT + D&A (DFC 6.01.01.02)"),
                                  _fmt(m.get("ebitda"),            "brl")],
            [_label("Lucro Líquido",
                    "Lucro Líquido = DRE 3.09 (Resultado do período)"),
                                  _fmt(m.get("lucro_liquido"),     "brl")],
            [_label("Margem Bruta",
                    "Margem Bruta = Lucro Bruto / Receita Líquida"),
                                  _fmt(r.get("marg_bruta"),        "pct")],
            [_label("Margem EBITDA",
                    "Margem EBITDA = EBITDA / Receita Líquida"),
                                  _fmt(r.get("marg_ebitda"),       "pct")],
            [_label("Margem Líquida",
                    "Margem Líquida = Lucro Líquido / Receita Líquida"),
                                  _fmt(r.get("marg_liquida"),      "pct")],
            [_label("Ativo Total",
                    "Ativo Total = BPA 1"),
                                  _fmt(m.get("ativo_total"),       "brl")],
            [_label("Patrimônio Liq.",
                    "PL = BPP 2.03"),
                                  _fmt(m.get("patrimonio_liquido"),"brl")],
            [_label("Caixa",
                    "Caixa = BPA 1.01.01"),
                                  _fmt(m.get("caixa"),             "brl")],
            [_label("Divida Bruta",
                    "Dívida Bruta = BPP 2.01.04 + 2.02.01"),
                                  _fmt(m.get("divida_bruta"),      "brl")],
            [_label("FCO",
                    "Fluxo de Caixa Operacional = DFC 6.01"),
                                  _fmt(m.get("fco"),               "brl")],
            [_label("FCI",
                    "Fluxo de Caixa de Investimento = DFC 6.02"),
                                  _fmt(m.get("fci"),               "brl")],
        ]
        sections.append({
            "title": "Latest Annual Summary",
            "type": "table",
            "columns": ["Indicador", "Valor"],
            "rows": rows,
        })

    # Quarterly trend table (oldest-first reversed for display newest-first)
    if quarterly_periods:
        trend_rows = []
        for p in reversed(quarterly_periods):
            m = p.get("metrics") or {}
            trend_rows.append([
                p.get("period", "—"),
                _fmt(m.get("receita_liquida"), "brl"),
                _fmt(m.get("ebitda"),          "brl"),
                _fmt(m.get("lucro_liquido"),   "brl"),
            ])
        sections.append({
            "title": "Quarterly Trend",
            "type": "table",
            "columns": ["Período", "Receita", "EBITDA", "Lucro Liq."],
            "rows": trend_rows,
        })

    # [v1.16] Freshness tables removed from Overview — the freshness footer
    # at the dashboard level (built by modes/dashboard.py) shows the last
    # sync timestamp + last synced period in a compact single-line format.
    # No need for two bulky tables here.
    return sections


# ── Tab 2: Indicadores (ratio_grid) ──────────────────────────────────────────

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
    "revenue_cagr_3y", "revenue_cagr_5y",
    "earnings_cagr_3y", "earnings_cagr_5y",
    "gross_profit_cagr_3y", "gross_profit_cagr_5y",
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

def _group_metrics_by_prefix(items: list[dict], category_label: str = "") -> list[dict]:
    """Group metric items by their label prefix (EV/, P/, ROE, etc.).

    Items with labels starting with "EV/" go into "EV (Enterprise Value)".
    Items with labels starting with "P/" go into "P/ (Price)".
    Growth items split by underlying metric (Receita/Lucro Líq./Resultado Bruto).
    CAGR items join the same per-metric group as their simple-growth siblings.
    Leverage items (category_label == "Endividamento") are split into
    "Ratios" (D/E, FCO/Dívida, Dív. Bruta/PL, Alavancagem Financeira) and
    "Multiples/Coverage" (Dív. Líq/EBITDA, DL/EBIT, Cobertura de Juros,
    Altman Z-Score) so they get separate charts with similar y-axis scales.
    Everything else goes into a group named after the category_label
    (e.g. "Liquidez", "Tributos") instead of the generic "Outros".

    [new commit] The "Outros" bucket is named after the category_label
    parameter (e.g. "Liquidez", "Endividamento", "Tributos"). User feedback:
    "box Outros - should be liquidez". For growth, keeps "Outros Crescimento".

    [v1.25] Added CAGR grouping (CAGR Receita/Lucro/Resultado Bruto join
    the matching simple-growth group), leverage 2-way split, and ROI in
    the Retorno group. Items must carry a "metric_name" field for the
    leverage split (other branches fall back to label-only matching).
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        label = item.get("label", "")
        metric_name = item.get("metric_name", "")
        if label.startswith("EV/"):
            gname = "EV (Enterprise Value)"
        elif label.startswith("P/"):
            gname = "P/ (Price)"
        elif label.startswith("Marg."):
            gname = "Margens"
        elif label.startswith("Giro"):
            gname = "Giro"
        elif label in ("ROE", "ROA", "ROIC", "ROI"):
            gname = "Retorno"
        elif (label.startswith("Crescimento Receita")
              or label.startswith("CAGR Receita")):
            gname = "Receita"
        elif (label.startswith("Crescimento Lucro")
              or label.startswith("CAGR Lucro")):
            gname = "Lucro Líquido"
        elif (label.startswith("Crescimento Resultado")
              or label.startswith("CAGR Resultado")):
            gname = "Resultado Bruto"
        elif label.startswith("Crescimento") or label.startswith("CAGR"):
            gname = "Outros Crescimento"
        elif category_label == "Endividamento":
            # [v1.25] Split leverage into "Ratios" and "Multiples/Coverage"
            # so each gets its own chart with a sensible y-axis range.
            # Ratios  → 0-2 range (D/E, FCO/Dívida, Dív. Bruta/PL, Alavancagem).
            # Multiples → 0-10+ range (Dív.Líq/EBITDA, DL/EBIT, Cobertura, Altman).
            if metric_name in {"debt_equity", "cash_flow_to_debt",
                               "gross_debt_equity", "financial_leverage"}:
                gname = "Ratios"
            else:
                gname = "Multiples/Coverage"
        else:
            # [new commit] Use the category label instead of generic "Outros"
            gname = category_label if category_label else "Outros"
        groups.setdefault(gname, []).append(item)

    # [new commit] Sort items WITHIN each growth group by horizon:
    # 3M first (key=0), then 1A (key=1), then 5A (key=3). User feedback:
    # "3M / 1A / 5A — currently sorted alphabetically (1A, 3M, 5A), want 3M
    # first". The registry's list_metrics_by_category() returns metric names
    # sorted alphabetically, so 1A ends up first by default — this re-sort
    # restores the intended chronological order.
    # [v1.25] Added "3A": 2 so CAGR 3Y sits between 1A and 5A.
    _GROWTH_HORIZON_ORDER = {
        "3M": 0, "1A": 1, "3A": 2, "5A": 3, "1Y": 1, "5Y": 3,
    }
    growth_groups = {"Receita", "Lucro Líquido", "Resultado Bruto",
                     "Outros Crescimento"}
    for gname in growth_groups:
        if gname in groups:
            def _horizon_key(item: dict) -> int:
                lbl = item.get("label", "")
                # Match trailing horizon token (e.g. "Crescimento Receita 3M").
                for tok, key in _GROWTH_HORIZON_ORDER.items():
                    if lbl.endswith(" " + tok) or lbl.endswith(tok):
                        return key
                return 99
            groups[gname].sort(key=_horizon_key)

    # Return in a sensible order
    order = [
        "EV (Enterprise Value)", "P/ (Price)", "Retorno", "Margens",
        "Giro", "Ratios", "Multiples/Coverage",
        "Receita", "Lucro Líquido", "Resultado Bruto",
        "Outros Crescimento", "Outros",
    ]
    result = []
    for gname in order:
        if gname in groups:
            result.append({"label": gname, "items": groups[gname]})
    # Add any groups not in the order list (preserves insertion order)
    for gname, gitems in groups.items():
        if gname not in order:
            result.append({"label": gname, "items": gitems})
    return result


def _build_category_items(category: str, ratios_payload: dict) -> tuple[list[dict], str | None]:
    """[v1.25] Build a list of ratio_grid items for a single category.

    Returns ``(items, cat_label)`` where each item has keys:
    ``label``, ``value``, ``value_raw``, ``metric_name``, ``tooltip``.
    Returns ``([], None)`` when the category has no plottable metrics.

    Used by both ``build_indicadores_section`` (per-category subtabs +
    "Todas" subtab) and ``build_crescimento_sections`` (growth ratio_grid
    moved out of Indicadores in v1.25).
    """
    try:
        from skills.cvm.calculations._registry import (
            METRICS, list_metrics_by_category,
        )
    except Exception:
        return [], None
    metrics_in_cat = list_metrics_by_category(category)
    if not metrics_in_cat:
        return [], None
    items: list[dict] = []
    for metric_name in metrics_in_cat:
        # Exclude raw-number metrics (working_capital) — they're not ratios.
        if metric_name in _INDICADORES_EXCLUDE:
            continue
        spec = METRICS.get(metric_name)
        if not spec:
            continue
        value = ratios_payload.get(metric_name)
        fmt_spec = "pct" if metric_name in _RATIO_PCT_KEYS else "num"
        label = _METRIC_LABELS.get(metric_name, spec.ratio_label)
        tooltip = _get_tooltip(metric_name, spec)
        items.append({
            "label": label,
            "value": _fmt(value, fmt_spec),
            # [v1.16.1] Store raw numeric value for chart builders.
            # Avoids fragile parsing of formatted strings (PT-BR "1.234,56"
            # breaks float() — was a P0 bug).
            "value_raw": float(value) if value is not None else None,
            # [v1.25] metric_name kept on the item so _group_metrics_by_prefix
            # can split leverage into Ratios/Multiples, and so valuation
            # charts can exclude BRL-value metrics (dcf_intrinsic_value,
            # graham_number).
            "metric_name": metric_name,
            "tooltip": tooltip,
        })
    if not items:
        return [], None
    cat_label = _RATIO_CATEGORY_LABELS.get(category, category.capitalize())
    return items, cat_label


def _build_group_bar_chart(
    gname: str, gitems: list[dict], category: str = "",
) -> dict | None:
    """[v1.25] Build a bar chart for a single ratio_grid box group.

    Scales 0-1 fractions to 0-100 percentages for display (using
    ``_RATIO_PCT_KEYS`` as the source of truth — more reliable than the
    previous ``abs(raw) < 1`` heuristic that mis-scaled growth values
    like 1.5 = 150%).

    Returns ``None`` when no plottable items (all values None).

    For valuation, the chart title comes from ``_VALUATION_CHART_TITLES``
    and the description from ``_VALUATION_CHART_DESCRIPTIONS`` — both
    honor the 3-group split the user named explicitly in the v1.25 spec
    (EV / P/ / Indicadores de Valor).
    """
    chart_labels: list[str] = []
    chart_values: list[float] = []
    for item in gitems:
        raw = item.get("value_raw")
        if raw is None:
            continue
        # Scale fractions (0-1) to percentages (0-100) for chart display.
        # Use _RATIO_PCT_KEYS as the source of truth (handles values >1.0
        # like 150% growth that the abs(raw) < 1 heuristic missed).
        metric_name = item.get("metric_name", "")
        if metric_name in _RATIO_PCT_KEYS:
            raw = raw * 100
        chart_labels.append(item["label"])
        chart_values.append(raw)
    if not chart_labels:
        return None

    color = _GROUP_CHART_COLORS.get(gname, "#0d9488")
    if category == "valuation":
        chart_title = _VALUATION_CHART_TITLES.get(gname, gname)
        chart_desc = _VALUATION_CHART_DESCRIPTIONS.get(
            gname, f"Valores numéricos: {gname}.")
    else:
        chart_title = gname
        chart_desc = f"Valores numéricos: {gname}."

    return {
        "type": "chart",
        "title": chart_title,
        "description": chart_desc,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": chart_labels,
                "datasets": [{
                    "label": gname,
                    "data": chart_values,
                    "backgroundColor": color,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {}}},
                "plugins": {
                    "title": {"display": True, "text": chart_title},
                },
            },
        },
    }


def build_indicadores_section(today: str, ratios_payload: dict) -> dict:
    """Build the Indicadores tab as a ``type: "subtabs"`` section.

    [v1.16] First sub-tab "Todas" shows ALL categories in one ratio_grid.
    Then individual category sub-tabs follow, each with items sub-grouped
    by prefix (EV/, P/, Retorno, Margens, etc.) within the ratio_grid.

    [v1.18] Each category subtab now also includes a bar chart showing
    the numeric values of that category's metrics — visual comparison
    alongside the ratio_grid.

    [v1.25] Charts split per ratio_grid box group (one chart per group,
    not one giant chart per category). Valuation gets 3 charts (EV / P/
    / Indicadores de Valor), excluding DCF Intrinsic + Graham Number
    (BRL values that break the y-axis scale). Growth subtab removed —
    moved to the dedicated Crescimento tab.
    """
    sub_tabs: list[dict] = []

    # First sub-tab: "Todas" — all categories in one ratio_grid.
    all_cats: list[dict] = []
    for category in _INDICADORES_CATEGORIES:
        items, cat_label = _build_category_items(category, ratios_payload)
        if items:
            all_cats.append({"label": cat_label, "items": items})
    if all_cats:
        sub_tabs.append({
            "name": "Todas",
            "sections": [{
                "title": f"Todos os Indicadores (as of {today})",
                "description": "Passe o mouse sobre cada indicador para ver a fórmula e explicação (ⓘ).",
                "type": "ratio_grid",
                "categories": all_cats,
            }],
        })

    # Individual category sub-tabs with prefix sub-grouping + per-group charts.
    for category in _INDICADORES_CATEGORIES:
        items, cat_label = _build_category_items(category, ratios_payload)
        if not items:
            continue
        # For valuation, the else bucket is "Indicadores de Valor" so the
        # 3 groups are: EV / P/ / Indicadores de Valor (matches the chart
        # titles the user named in the v1.25 spec).
        if category == "valuation":
            grouped = _group_metrics_by_prefix(
                items, category_label="Indicadores de Valor")
        else:
            grouped = _group_metrics_by_prefix(items, category_label=cat_label)

        sub_sections: list[dict] = [{
            "title": f"{cat_label} (as of {today})",
            "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
            "type": "ratio_grid",
            "categories": grouped,
        }]

        # [v1.25] One chart per group (split by box groups, not one
        # giant chart per category). For valuation, exclude BRL-value
        # metrics (DCF Intrinsic + Graham Number) from charts — they
        # break the y-axis scale (R$ tens vs ratio multiples).
        for group in grouped:
            gname = group["label"]
            gitems = group["items"]
            if category == "valuation":
                gitems = [it for it in gitems
                          if it.get("metric_name") not in _VALUATION_CHART_EXCLUDE]
            chart_section = _build_group_bar_chart(gname, gitems, category)
            if chart_section is not None:
                sub_sections.append(chart_section)

        sub_tabs.append({
            "name": cat_label,
            "sections": sub_sections,
        })

    # Fallback when the registry can't be loaded — show whatever is in
    # ratios_payload as a single flat ratio_grid.
    if not sub_tabs:
        items = []
        for k, v in sorted(ratios_payload.items()):
            if k in ("date", "error"):
                continue
            fmt_spec = "pct" if k in _RATIO_PCT_KEYS else "num"
            label = _METRIC_LABELS.get(k, k)
            items.append({"label": label, "value": _fmt(v, fmt_spec)})
        if items:
            sub_tabs.append({
                "name": "Indicadores",
                "sections": [{
                    "title": f"Indicadores (as of {today})",
                    "type": "ratio_grid",
                    "categories": [{"label": "Indicadores", "items": items}],
                }],
            })

    if not sub_tabs:
        return {"type": "text", "text": "Nenhum indicador disponível."}

    return {
        "title": f"Indicadores (as of {today})",
        "type": "subtabs",
        "tabs": sub_tabs,
    }


# ── Tab 3: Crescimento (growth table + bar chart) ────────────────────────────

def _period_date(p: dict) -> str:
    """Extract a YYYY-MM-DD date from an annual period dict.

    Falls back to "{period}-12-31" when data_fim_exerc is absent (annual
    periods always end on Dec 31).
    """
    d = p.get("data_fim_exerc")
    if d:
        return str(d)[:10]
    period = p.get("period")
    if period:
        return f"{period}-12-31"
    return "1900-01-01"


def _build_metric_periods(
    annual_periods: list[dict], metric_key: str,
) -> list[dict]:
    """Build a [{"date": str, "value": float|None}, ...] list for growth_helpers.

    Walks annual_periods (any order), extracts the named metric from each
    period's ``metrics`` dict, and returns a list sorted oldest-first.
    """
    out: list[dict] = []
    for p in annual_periods:
        if not p.get("period"):
            continue
        val = (p.get("metrics") or {}).get(metric_key)
        out.append({
            "date": _period_date(p),
            "value": float(val) if val is not None else None,
        })
    out.sort(key=lambda x: x["date"])
    return out


def _build_growth_ratio_grid_section(ratios_payload: dict, today: str) -> dict | None:
    """[v1.25] Build a ratio_grid section showing ALL growth metrics.

    Moved here from the Indicadores tab (where the "Crescimento" subtab
    was removed in v1.25). Shows:

      - Crescimento 3M / 1A / 5A (simple growth) for Receita, Lucro
        Líquido, Resultado Bruto
      - CAGR 3A / 5A (compound annual) for the same three metrics
      - Taxa de Retenção + Crescimento Sustentável (in "Outros Crescimento")

    Grouped via ``_group_metrics_by_prefix`` into per-metric boxes
    (Receita / Lucro Líquido / Resultado Bruto / Outros Crescimento)
    with horizon-sorted items inside each box.

    Returns ``None`` when no growth metrics are registered (registry
    unavailable or empty).
    """
    items, _ = _build_category_items("growth", ratios_payload)
    if not items:
        return None
    grouped = _group_metrics_by_prefix(items, category_label="Crescimento")
    return {
        "title": f"Crescimento — Indicadores (as of {today})",
        "description": (
            "Crescimento 3M/1A/5A (simples) + CAGR 3A/5A (composto) + "
            "Taxa de Retenção e Crescimento Sustentável. Passe o mouse "
            "sobre cada indicador para ver a fórmula (ⓘ)."
        ),
        "type": "ratio_grid",
        "categories": grouped,
    }


def build_crescimento_sections(
    latest_annual_period: dict | None,
    annual_periods: list[dict],
    quarterly_periods: list[dict] | None = None,
    ratios_payload: dict | None = None,
) -> list[dict]:
    """Build the Crescimento tab: growth ratio_grid + 3M/1Y/5Y table + bar charts.

    [new commit] MAJOR REWRITE — delegates to ratios_payload (computed via
    the calculations registry + FIXED growth_at anchoring). This eliminates:
      - F8: lexicographic quarter sort bug (no longer sorts quarters)
      - F10: duplicate growth logic (now uses same path as Indicadores)
      - F19: zero-guard too strict (delegated to growth_helpers)
    The old implementation called growth_at() on ANNUAL periods + had its
    own _qoq_growth with the lexicographic sort bug. Now both 3M/1Y/5Y
    come from ratios_payload which uses TTM periods + the anchored prior
    search (consistent with the historical dashboard).

    [v1.25] Added a growth ratio_grid at the TOP — moved here from the
    Indicadores tab (where the "Crescimento" subtab was removed). The
    ratio_grid shows 3M/1A/5A growth + CAGR 3A/5A + retention + sustainable
    growth, grouped by underlying metric. The existing 3M/1Y/5Y table and
    3 per-metric bar charts are kept below the ratio_grid.
    """
    sections: list[dict] = []

    rp = ratios_payload or {}

    # [v1.25] Growth ratio_grid at the TOP — moved from Indicadores tab.
    # Includes 3M/1A/5A growth + CAGR 3A/5A + retention + sustainable growth.
    from datetime import date as _date
    today = _date.today().isoformat()
    growth_grid = _build_growth_ratio_grid_section(rp, today)
    if growth_grid is not None:
        sections.append(growth_grid)

    # Pull growth values from ratios_payload (computed by compute_all_ratios
    # with the FIXED growth_at anchoring on curr_p date, not target_date).
    rev_3m = rp.get("revenue_growth_3m")
    rev_1y = rp.get("revenue_growth_1y")
    rev_5y = rp.get("revenue_growth_5y")
    gp_3m = rp.get("gross_profit_growth_3m")
    gp_1y = rp.get("gross_profit_growth_1y")
    gp_5y = rp.get("gross_profit_growth_5y")
    ni_3m = rp.get("net_income_growth_3m")
    ni_1y = rp.get("net_income_growth_1y")
    ni_5y = rp.get("net_income_growth_5y")

    # If ALL simple-growth values are None, skip the table + per-metric
    # charts (the ratio_grid above may still show CAGR / retention values).
    all_vals = [rev_3m, rev_1y, rev_5y, gp_3m, gp_1y, gp_5y, ni_3m, ni_1y, ni_5y]
    if all(v is None for v in all_vals):
        if not growth_grid:
            sections.append({
                "type": "text",
                "text": "Crescimento indisponível — sem dados de receita/lucro TTM.",
            })
        return sections

    rows = [
        ["Receita Líquida",   _fmt(rev_3m, "pct"), _fmt(rev_1y, "pct"), _fmt(rev_5y, "pct")],
        ["Lucro Bruto",       _fmt(gp_3m, "pct"), _fmt(gp_1y, "pct"), _fmt(gp_5y, "pct")],
        ["Lucro Líquido",     _fmt(ni_3m, "pct"), _fmt(ni_1y, "pct"), _fmt(ni_5y, "pct")],
    ]
    sections.append({
        "title": "Crescimento (3M / 1Y / 5Y)",
        "description": (
            "Crescimento de Receita, Lucro Bruto e Lucro Líquido baseado "
            "em TTM (trailing twelve months). 3M = TTM atual vs TTM há 3 "
            "meses; 1Y e 5Y usam janelas de 1 e 5 anos com tolerância de gap."
        ),
        "type": "table",
        "columns": ["Métrica", "3M", "1Y", "5Y"],
        "rows": rows,
        "note": (
            "Valores calculados via calculations registry (growth_at com "
            "anchoring no período atual). Consistente com o dashboard "
            "histórico."
        ),
    })

    # [new commit] SPLIT chart: previously ONE combined bar chart with 3
    # datasets (3M/1Y/5Y) × 3 metric labels (Receita/Lucro Bruto/Lucro
    # Líquido). User feedback: "3 separate charts — one per metric
    # (Receita, Lucro Líquido, Resultado Bruto), each showing 3M/1Y/5Y as
    # bars." Now we emit 3 separate bar charts, each with 3 bars (3M/1Y/5Y)
    # for a single metric. Makes cross-horizon comparison within a metric
    # easier (no longer competing on the same axis as the other metrics).
    _COLORS = {"3M": "#a855f7", "1A": "#22c55e", "5A": "#3b82f6"}

    def _metric_chart(
        metric_label: str, vals: list[float | None],
    ) -> dict | None:
        """Build a single-metric 3-bar chart (3M / 1A / 5Y)."""
        if all(v is None for v in vals):
            return None
        labels = ["3M", "1A", "5A"]
        data = [(v * 100 if v is not None else None) for v in vals]
        return {
            "type": "chart",
            "title": f"Crescimento {metric_label} (3M / 1A / 5A)",
            "description": (
                f"Crescimento percentual de {metric_label} nos três "
                "horizontes temporais (3M = QoQ TTM, 1A = anual, 5A = "
                "5 anos). Barras ausentes indicam dados insuficientes "
                "para o cálculo."
            ),
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": f"{metric_label} (%)",
                        "data": data,
                        "backgroundColor": [
                            _COLORS["3M"], _COLORS["1A"], _COLORS["5A"],
                        ],
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "y": {
                            "ticks": {},
                            "title": {"display": True, "text": "Crescimento (%)"},
                        },
                    },
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": f"{metric_label} — Crescimento por Horizonte",
                        },
                    },
                },
            },
        }

    for metric_label, vals in [
        ("Receita Líquida",   [rev_3m, rev_1y, rev_5y]),
        ("Lucro Bruto",       [gp_3m, gp_1y, gp_5y]),
        ("Lucro Líquido",     [ni_3m, ni_1y, ni_5y]),
    ]:
        chart = _metric_chart(metric_label, vals)
        if chart is not None:
            sections.append(chart)

    return sections


# ── Tab 4: Balanço (BPA + BPP subtabs) ───────────────────────────────────────

def _statement_table_section(title: str, accounts_dict: dict) -> dict:
    """Build a `type: "table"` section from a {codigo: {label, section, valor_brl}} dict.

    Groups by section, with one row per account code. Values are pre-formatted
    as compact BRL.
    """
    rows: list[list[str]] = []
    # Preserve insertion order; group by section visually via a header row.
    last_section: str | None = None
    for codigo, acc in accounts_dict.items():
        section = acc.get("section") or ""
        if section and section != last_section:
            rows.append([f"— {section} —", ""])
            last_section = section
        rows.append([
            codigo,
            acc.get("label") or codigo,
            _fmt(acc.get("valor_brl"), "brl"),
        ])
    return {
        "title": title,
        "type": "table",
        "columns": ["Código", "Descrição", "Valor (BRL)"],
        "rows": rows,
    }


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


def build_multi_period_table(
    title: str, periods: list[dict], statement_type: str,
) -> dict | None:
    """[v1.23 F3 / v1.24] Build a multi-period comparison table for a statement.

    Shows up to 20 periods (annual OR quarterly) side-by-side so users can
    compare each account code across periods without flipping tabs. Used as
    the FIRST section in each of the Balanço / DRE / DFC / DVA tabs.

    [v1.24] Changes vs v1.23:
      - Cap raised from 4 → 20 periods (quarterly mode fetches up to 5Y).
      - Period labels now derived via ``_format_period_label``: "2023" for
        annual, "2T2026" for quarterly.
      - ``wide: True`` flag set on the section when >6 periods so the
        template wraps the table in ``overflow-x: auto``.
      - Note caption is period-aware ("anuais" vs "trimestrais").

    Args:
        title: table title.
        periods: list of period dicts (each has ``period`` label + ``accounts``
            dict of ``{codigo: {label, section, valor_brl}}``). Periods are
            assumed to be newest-first (the standard statement-mode order).
        statement_type: "BPA" / "BPP" / "DRE" / "DFC" / "DVA" — used for the
            note caption.

    Returns:
        A ``type: "table"`` section, or None when no periods / no accounts.
    """
    # [v1.25 v5] Don't filter out periods with empty accounts — include ALL
    # periods so the table has consistent column count (20 quarters) across
    # all tabs. Periods with no data show "—" for each code.
    valid_periods = [p for p in (periods or []) if p.get("data_fim_exerc") or p.get("period")]
    if not valid_periods:
        return None
    # [v1.25 v2] Sort newest-first (descending) using _period_sort_key.
    # Was relying on caller order which was inconsistent (quarterly asc, annual desc).
    valid_periods.sort(key=_period_sort_key, reverse=True)
    # Cap at 20 periods (newest-first).
    valid_periods = valid_periods[:20]

    period_labels = [_format_period_label(p) for p in valid_periods]
    columns = ["Código", "Descrição"] + period_labels

    # Build a unified code→{label, section} map preserving first-seen order.
    code_meta: dict[str, dict] = {}
    for p in valid_periods:
        for codigo, acc in (p.get("accounts") or {}).items():
            if codigo not in code_meta:
                code_meta[codigo] = {
                    "label": acc.get("label") or codigo,
                    "section": acc.get("section") or "",
                }

    rows: list[list] = []
    last_section: str | None = None
    n_periods = len(valid_periods)
    for codigo, meta in code_meta.items():
        section = meta["section"]
        if section and section != last_section:
            # Section header row — span all columns.
            header_row = [f"— {section} —", ""]
            header_row.extend([""] * n_periods)
            rows.append(header_row)
            last_section = section
        row: list = [codigo, meta["label"]]
        for p in valid_periods:
            acc = (p.get("accounts") or {}).get(codigo) or {}
            val = acc.get("valor_brl")
            row.append(_fmt(val, "brl") if val is not None else "—")
        rows.append(row)

    # Detect period type for the caption
    is_quarterly = any(p.get("quarter") is not None for p in valid_periods)
    period_word = "trimestrais" if is_quarterly else "anuais"

    return {
        "title": title,
        "type": "table",
        "columns": columns,
        "rows": rows,
        # [v1.24] Wrap wide tables (≥7 columns → "Código" + "Descrição" + 5+ periods)
        # in a horizontally-scrollable container so the layout doesn't blow out.
        "wide": n_periods > 5,
        "note": (
            f"Comparativo de {n_periods} período(s) {period_word} ({statement_type}). "
            "Valores em R$ (formato compacto)."
        ),
    }


def _merge_bpa_bpp_periods(
    bpa_periods: list[dict], bpp_periods: list[dict],
) -> list[dict]:
    """[v1.24] Merge BPA + BPP periods into a single list with combined accounts.

    For each period present in EITHER input, merge the accounts dicts (BPA
    accounts first, then BPP accounts — same order as the Completo sub-tab
    visual: Ativo section first, then Passivo). Periods are returned
    newest-first, keyed by ``period`` (or ``data_fim_exerc`` as fallback).

    Used by the Balanço "Completo" sub-tab so the multi-period comparison
    table shows both sides of the balance sheet side-by-side across periods.
    """
    by_period: dict[str, dict] = {}
    for p in bpa_periods + bpp_periods:
        period_key = p.get("period") or p.get("data_fim_exerc") or ""
        if not period_key:
            continue
        if period_key not in by_period:
            by_period[period_key] = {
                "period": period_key,
                "data_fim_exerc": p.get("data_fim_exerc"),
                "year": p.get("year"),
                "quarter": p.get("quarter"),
                "accounts": {},
            }
        # Merge accounts (BPA first, then BPP — preserves visual grouping)
        for codigo, acc in (p.get("accounts") or {}).items():
            by_period[period_key]["accounts"][codigo] = acc

    return sorted(
        by_period.values(),
        key=lambda p: (p.get("year") or 0, p.get("quarter") or 0),
        reverse=True,
    )


def _build_period_toggle_sections(
    label: str,
    annual_periods: list[dict],
    quarterly_periods: list[dict] | None,
    statement_type: str,
    annual_chart: dict | list[dict] | None = None,
    quarterly_chart: dict | list[dict] | None = None,
) -> list[dict]:
    """[v1.25 v3] Build a section list with optional period toggle.

    - When ``quarterly_periods`` is non-empty: returns a single
      ``type: "period_toggle"`` section wrapping two ``build_multi_period_table``
      calls (annual + quarterly) PLUS optional charts. Quarterly visible by default.
    - When ``quarterly_periods`` is empty/None: returns just the annual
      multi-period table + annual chart (no toggle).

    Args:
        label: statement label used in table titles.
        annual_periods: annual period dicts.
        quarterly_periods: quarterly period dicts, or None/[] when unavailable.
        statement_type: BPA / BPP / DRE / DFC / DVA.
        annual_chart: optional chart section(s) for the annual panel.
        quarterly_chart: optional chart section(s) for the quarterly panel.

    Returns:
        List of 0-1 sections.
    """
    annual_table = build_multi_period_table(
        f"{label} — Comparativo Anual", annual_periods, statement_type)

    # Normalize charts to lists
    annual_charts = []
    if annual_chart:
        annual_charts = annual_chart if isinstance(annual_chart, list) else [annual_chart]
    quarterly_charts = []
    if quarterly_chart:
        quarterly_charts = quarterly_chart if isinstance(quarterly_chart, list) else [quarterly_chart]

    if quarterly_periods:
        quarterly_table = build_multi_period_table(
            f"{label} — Comparativo Trimestral", quarterly_periods, statement_type)
        if annual_table or quarterly_table:
            annual_secs = ([annual_table] if annual_table else []) + annual_charts
            quarterly_secs = ([quarterly_table] if quarterly_table else []) + quarterly_charts
            return [{
                "type": "period_toggle",
                "annual_sections": annual_secs,
                "quarterly_sections": quarterly_secs,
            }]
        return []

    if annual_table:
        return [annual_table] + annual_charts
    return []


def build_balanco_section(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
    subtab_charts_annual: dict | None = None,
    subtab_charts_quarterly: dict | None = None,
) -> dict:
    """Build the Balanço tab as a `type: "subtabs"` section with BPA + BPP.

    [v1.25 v4] Per-subtab time-series charts are now INSIDE the
    period_toggle. ``subtab_charts_annual`` / ``subtab_charts_quarterly``
    are dicts mapping subtab name ("Completo" / "BPA" / "BPP") to a list
    of chart sections built from annual + quarterly BPA/BPP results
    respectively. The 6 stacked-bar charts (2 Completo + 2 BPA + 2 BPP,
    each with absolute + percentage variants) are now passed into
    ``_build_period_toggle_sections`` so they switch with the toggle.
    Removed the dashboard's separate ``balanco_sections.extend(charts)``
    calls — those charts now live inside the toggle.

    [v1.24] Quarterly support:
      - Accepts optional ``bpa_result_q`` / ``bpp_result_q`` (quarterly
        statement results from ``_fetch_all_statements(period="quarterly")``).
      - Each sub-tab (Completo / BPA / BPP) wraps its multi-period table in a
        ``type: "period_toggle"`` section so the user can switch between
        annual + quarterly views. When no quarterly data is provided, the
        toggle is omitted (backward-compatible with v1.23 callers).
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table per sub-tab. The Completo
        sub-tab now uses ``build_multi_period_table()`` with merged BPA+BPP
        periods (was a single-period merge in v1.23).
    """
    sub_tabs: list[dict] = []
    sca = subtab_charts_annual or {}
    scq = subtab_charts_quarterly or {}

    bpa_periods = (bpa_result or {}).get("periods") or []
    bpp_periods = (bpp_result or {}).get("periods") or []
    bpa_periods_q = (bpa_result_q or {}).get("periods") or []
    bpp_periods_q = (bpp_result_q or {}).get("periods") or []

    # ── "Completo" sub-tab: BPA + BPP merged, multi-period ──────────────
    if bpa_periods and bpp_periods:
        merged_annual = _merge_bpa_bpp_periods(bpa_periods, bpp_periods)
        merged_quarterly = (
            _merge_bpa_bpp_periods(bpa_periods_q, bpp_periods_q)
            if (bpa_periods_q and bpp_periods_q) else []
        )
        completo_sections = _build_period_toggle_sections(
            "Balanço Completo", merged_annual, merged_quarterly, "BPA+BPP",
            annual_chart=sca.get("Completo"),
            quarterly_chart=scq.get("Completo"))
        if completo_sections:
            sub_tabs.append({"name": "Completo", "sections": completo_sections})

    # ── BPA sub-tab ─────────────────────────────────────────────────────
    if bpa_periods:
        bpa_sections = _build_period_toggle_sections(
            "Ativo", bpa_periods, bpa_periods_q, "BPA",
            annual_chart=sca.get("BPA"),
            quarterly_chart=scq.get("BPA"))
        if bpa_sections:
            sub_tabs.append({"name": "BPA", "sections": bpa_sections})
    if not any(st["name"] == "BPA" for st in sub_tabs):
        sub_tabs.append({
            "name": "BPA",
            "sections": [{"type": "text",
                          "text": "BPA data unavailable for this company."}],
        })

    # ── BPP sub-tab ─────────────────────────────────────────────────────
    if bpp_periods:
        bpp_sections = _build_period_toggle_sections(
            "Passivo", bpp_periods, bpp_periods_q, "BPP",
            annual_chart=sca.get("BPP"),
            quarterly_chart=scq.get("BPP"))
        if bpp_sections:
            sub_tabs.append({"name": "BPP", "sections": bpp_sections})
    if not any(st["name"] == "BPP" for st in sub_tabs):
        sub_tabs.append({
            "name": "BPP",
            "sections": [{"type": "text",
                          "text": "BPP data unavailable for this company."}],
        })

    return {"type": "subtabs", "tabs": sub_tabs}


# ── Tab 5: DRE (table + margin trend chart) ──────────────────────────────────

def build_dre_sections(
    dre_result: dict,
    annual_periods: list[dict],
    latest_annual_period: dict | None,
    company: str | None = None,
    dre_result_q: dict | None = None,
    quarterly_periods: list[dict] | None = None,
) -> list[dict]:
    """Build the DRE tab: multi-period comparison table + 5Y margin trend chart.

    [v1.25 v4] ALL time-series charts are now INSIDE the period_toggle:
      - Trajetória de Receita e Lucro (trend)
      - Evolução das Margens (gross/EBIT/EBITDA/net line chart)
      - Receita, EBITDA e Lucro Líquido (absolute-values bar chart)
    Each has an annual version (built from ``annual_periods``) and a
    quarterly version (built from ``quarterly_periods`` when available).
    Removed the separate ``sections.append()`` calls for the margins and
    absolute-values charts — they're now part of the toggle's annual_chart
    / quarterly_chart lists.

    [v1.24] Quarterly support:
      - Accepts optional ``dre_result_q`` (quarterly DRE statement result).
      - The multi-period table is wrapped in a ``period_toggle`` section so
        the user can switch between annual + quarterly views.
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table.
      - Trend chart now prefers quarterly periods (when available) so the
        price-overlay line chart shows finer-grained movement.

    [v1.23 F4] Appends a statement-level trend chart (Receita/EBITDA/
    Lucro Líq. + price overlay on right axis) at the END of the sections.
    Backward-compatible: ``company`` is optional; when None the overlay is
    skipped.
    """
    sections: list[dict] = []

    dre_periods = (dre_result or {}).get("periods") or []
    dre_periods_q = (dre_result_q or {}).get("periods") or []
    q_periods = quarterly_periods or []

    # [v1.25 v3] Build annual + quarterly trend charts, pass into period_toggle.
    dre_annual_trend = build_statement_trend_chart(dre_periods, company, "DRE")
    dre_quarterly_trend = build_statement_trend_chart(dre_periods_q, company, "DRE") if dre_periods_q else None

    # [v1.25 v4] Build annual + quarterly margins charts.
    dre_annual_margins = _build_dre_margins_chart(annual_periods)
    dre_quarterly_margins = _build_dre_margins_chart(q_periods) if q_periods else None

    # [v1.25 v4] Build annual + quarterly absolute-values bar charts.
    dre_annual_abs = _build_dre_abs_chart(annual_periods, "Anual")
    dre_quarterly_abs = _build_dre_abs_chart(q_periods, "Trimestral") if q_periods else None

    # [v1.25 v4] Collect all annual charts + all quarterly charts (order:
    # trend first, then margins, then absolute-values bar chart — matches
    # the previous top-level ordering where trend was last, but inside the
    # toggle it makes more sense to lead with the trend chart).
    annual_charts = [c for c in
                     [dre_annual_trend, dre_annual_margins, dre_annual_abs]
                     if c is not None]
    quarterly_charts = [c for c in
                        [dre_quarterly_trend, dre_quarterly_margins, dre_quarterly_abs]
                        if c is not None]

    # [v1.24] Multi-period table (annual + quarterly via period_toggle) +
    # ALL time-series charts INSIDE toggle.
    sections.extend(_build_period_toggle_sections(
        "DRE", dre_periods, dre_periods_q, "DRE",
        annual_chart=annual_charts,
        quarterly_chart=quarterly_charts,
    ))

    # Fallback: latest_annual_period metrics table (DRE codes).
    if not sections and latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        r = latest_annual_period.get("ratios") or {}
        rows = [
            ["Receita Líquida",       _fmt(m.get("receita_liquida"),     "brl")],
            ["Lucro Bruto",           _fmt(m.get("lucro_bruto"),         "brl")],
            ["EBIT",                  _fmt(m.get("ebit"),                "brl")],
            ["D&A",                   _fmt(m.get("da"),                  "brl")],
            ["EBITDA",                _fmt(m.get("ebitda"),              "brl")],
            ["EBITDA Method",         str(m.get("ebitda_method") or "—")],
            ["Resultado Financeiro",  _fmt(m.get("resultado_financeiro"),"brl")],
            ["Lucro Líquido",         _fmt(m.get("lucro_liquido"),       "brl")],
            ["", ""],
            ["Margem Bruta",          _fmt(r.get("marg_bruta"),          "pct")],
            ["Margem EBIT",           _fmt(r.get("marg_ebit"),           "pct")],
            ["Margem EBITDA",         _fmt(r.get("marg_ebitda"),         "pct")],
            ["Margem Líquida",        _fmt(r.get("marg_liquida"),        "pct")],
        ]
        sections.append({
            "title": "DRE (Latest Annual)",
            "type": "table",
            "columns": ["Indicador", "Valor"],
            "rows": rows,
        })

    if not sections:
        sections.append({
            "type": "text",
            "text": "DRE data unavailable for this company.",
        })

    # [v1.25 v4] Margins chart + absolute-values chart + trend chart are now
    # ALL INSIDE the period_toggle (above). No separate sections.append calls.

    return sections


def _build_dre_margins_chart(periods: list[dict]) -> dict | None:
    """[v1.25 v4] Build the DRE margins evolution chart (gross/EBIT/EBITDA/net)
    from a list of period dicts. Works for BOTH annual + quarterly periods
    (each period must have a ``ratios`` dict with ``marg_*`` keys).

    Returns None if fewer than 2 periods or all margin values are None.
    Used by ``build_dre_sections`` to build annual + quarterly versions for
    the period_toggle.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    gross, operating, net, ebitda = [], [], [], []
    for p in sorted_periods:
        r = p.get("ratios") or {}
        gross.append(_pct_of(r.get("marg_bruta")))
        operating.append(_pct_of(r.get("marg_ebit")))
        net.append(_pct_of(r.get("marg_liquida")))
        ebitda.append(_pct_of(r.get("marg_ebitda")))
    if not any(v is not None for v in gross + operating + net + ebitda):
        return None
    return {
        "type": "chart",
        "title": "Evolução das Margens",
        "description": (
            "Margens Bruta, EBIT, EBITDA e Líquida ao longo do tempo. "
            "Mostra a trajetória da rentabilidade operacional."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Marg. Bruta",  "data": gross,
                     "borderColor": "#22c55e", "fill": False, "tension": 0.3},
                    {"label": "Marg. EBIT",   "data": operating,
                     "borderColor": "#3b82f6", "fill": False, "tension": 0.3},
                    {"label": "Marg. EBITDA", "data": ebitda,
                     "borderColor": "#f59e0b", "fill": False, "tension": 0.3},
                    {"label": "Marg. Líquida","data": net,
                     "borderColor": "#a855f7", "fill": False, "tension": 0.3},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "Margem (%)"}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": "Margens Operacionais ao Longo do Tempo"},
                },
            },
        },
    }


def _build_dre_abs_chart(periods: list[dict], period_label: str) -> dict | None:
    """[v1.25 v4] Build the Receita/EBITDA/Lucro Líquido absolute-value bar
    chart from a list of period dicts. Works for BOTH annual + quarterly
    periods (each period must have a ``metrics`` dict with ``receita_liquida``
    / ``ebitda`` / ``lucro_liquido`` keys).

    Args:
        periods: list of period dicts (annual or quarterly).
        period_label: "Anual" or "Trimestral" — used in the chart title.

    Returns None if fewer than 2 periods or all values are None.
    Used by ``build_dre_sections`` to build annual + quarterly versions for
    the period_toggle.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    revenue_abs, ebitda_abs, ni_abs = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        revenue_abs.append(_num_or_none(m.get("receita_liquida")))
        ebitda_abs.append(_num_or_none(m.get("ebitda")))
        ni_abs.append(_num_or_none(m.get("lucro_liquido")))
    if not any(v is not None for v in revenue_abs + ebitda_abs + ni_abs):
        return None
    return {
        "type": "chart",
        "title": f"Receita, EBITDA e Lucro Líquido ({period_label}, R$)",
        "description": (
            f"Valores absolutos {period_label.lower()} de Receita Líquida, "
            "EBITDA e Lucro Líquido. Barras agrupadas por período permitem "
            "comparar a magnitude de cada componente do resultado ao longo "
            "do tempo."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita Líquida", "data": revenue_abs,
                     "backgroundColor": "#0d9488"},
                    {"label": "EBITDA", "data": ebitda_abs,
                     "backgroundColor": "#f59e0b"},
                    {"label": "Lucro Líquido", "data": ni_abs,
                     "backgroundColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$"}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": "Receita, EBITDA e Lucro por Período"},
                },
            },
        },
    }


def _pct_of(value: Any) -> float | None:
    """Convert a fractional ratio (0.15) to a percentage number (15.0)."""
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


# ── Tab 6: DFC (table + stacked bar chart) ───────────────────────────────────

def build_dfc_sections(
    dfc_result: dict,
    annual_periods: list[dict],
    latest_annual_period: dict | None,
    company: str | None = None,
    dfc_result_q: dict | None = None,
    quarterly_periods: list[dict] | None = None,
) -> list[dict]:
    """Build the DFC tab: multi-period comparison table + 5Y FCO/FCI/FCF chart.

    [v1.25 v4] ALL time-series charts are now INSIDE the period_toggle:
      - Trajetória de FCO/FCI/FCF (trend)
      - Fluxos de Caixa (stacked bar — FCO/FCI/FCF)
      - FCO vs Lucro Líquido (earnings-quality line chart — moved here from
        ``build_dfc_quality_section`` so it switches with the toggle)
    Each has an annual version (built from ``annual_periods``) and a
    quarterly version (built from ``quarterly_periods`` when available).
    Removed the separate ``sections.append()`` calls for the stacked bar
    chart — it's now part of the toggle's annual_chart / quarterly_chart.

    The "Qualidade do Fluxo de Caixa" TABLE (TTM values) STAYS OUTSIDE the
    toggle — it's a point-in-time table, not a time-series. It continues to
    be produced by ``build_dfc_quality_section`` and appended to
    ``dfc_sections`` by the dashboard.

    [v1.24] Quarterly support:
      - Accepts optional ``dfc_result_q`` (quarterly DFC statement result).
      - The multi-period table is wrapped in a ``period_toggle`` section so
        the user can switch between annual + quarterly views.
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table.
      - Trend chart now prefers quarterly periods (when available).

    [v1.23 F4] Appends a DFC trend chart (FCO/FCI/FCF + price overlay on
    right axis) at the END of the sections. Backward-compatible.
    """
    sections: list[dict] = []

    dfc_periods = (dfc_result or {}).get("periods") or []
    dfc_periods_q = (dfc_result_q or {}).get("periods") or []
    q_periods = quarterly_periods or []

    # [v1.25 v3] Build annual + quarterly trend charts, pass into period_toggle.
    dfc_annual_trend = build_dfc_trend_chart(dfc_periods, company)
    dfc_quarterly_trend = build_dfc_trend_chart(dfc_periods_q, company) if dfc_periods_q else None

    # [v1.25 v4] Build annual + quarterly stacked-bar charts (FCO/FCI/FCF).
    dfc_annual_stacked = _build_dfc_stacked_chart(annual_periods)
    dfc_quarterly_stacked = _build_dfc_stacked_chart(q_periods) if q_periods else None

    # [v1.25 v4] Build annual + quarterly FCO-vs-Lucro-Líquido line charts
    # (earnings-quality divergence). Moved here from build_dfc_quality_section
    # so the chart switches with the toggle. The quality TABLE (TTM values)
    # stays in build_dfc_quality_section (point-in-time, not time-series).
    dfc_annual_fco_vs_ll = _build_dfc_fco_vs_ll_chart(annual_periods)
    dfc_quarterly_fco_vs_ll = _build_dfc_fco_vs_ll_chart(q_periods) if q_periods else None

    # [v1.25 v4] Collect all annual + quarterly charts (order: trend,
    # stacked bar, FCO vs LL).
    annual_charts = [c for c in
                     [dfc_annual_trend, dfc_annual_stacked, dfc_annual_fco_vs_ll]
                     if c is not None]
    quarterly_charts = [c for c in
                        [dfc_quarterly_trend, dfc_quarterly_stacked, dfc_quarterly_fco_vs_ll]
                        if c is not None]

    # [v1.24] Multi-period table + ALL time-series charts INSIDE period_toggle.
    sections.extend(_build_period_toggle_sections(
        "DFC", dfc_periods, dfc_periods_q, "DFC",
        annual_chart=annual_charts,
        quarterly_chart=quarterly_charts,
    ))

    if not sections and latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        rows = [
            ["FCO",  _fmt(m.get("fco"), "brl")],
            ["FCI",  _fmt(m.get("fci"), "brl")],
            ["FCF",  _fmt(m.get("fcf"), "brl")],
        ]
        sections.append({
            "title": "DFC (Latest Annual)",
            "type": "table",
            "columns": ["Indicador", "Valor"],
            "rows": rows,
        })
    if not sections:
        sections.append({
            "type": "text",
            "text": "DFC data unavailable for this company.",
        })

    # [v1.25 v4] Stacked bar chart + FCO vs LL chart + trend chart are now
    # ALL INSIDE the period_toggle (above). No separate sections.append calls.

    return sections


def _build_dfc_stacked_chart(periods: list[dict]) -> dict | None:
    """[v1.25 v4] Build the DFC stacked-bar chart (FCO/FCI/FCF) from a list
    of period dicts. Works for BOTH annual + quarterly periods (each period
    must have a ``metrics`` dict with ``fco`` / ``fci`` / ``fcf`` keys).

    Returns None if fewer than 2 periods or all values are None.
    Used by ``build_dfc_sections`` to build annual + quarterly versions for
    the period_toggle.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    fco, fci, fcf = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        fco.append(_num_or_none(m.get("fco")))
        fci.append(_num_or_none(m.get("fci")))
        fcf.append(_num_or_none(m.get("fcf")))
    if not any(v is not None for v in fco + fci + fcf):
        return None
    return {
        "type": "chart",
        "title": "Fluxos de Caixa (empilhado)",
        "description": (
            "Fluxo de Caixa Operacional (FCO), de Investimento (FCI) e de "
            "Financiamento (FCF) ao longo do tempo. Barras empilhadas "
            "mostram a composição total do fluxo de caixa."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "FCO", "data": fco, "backgroundColor": "#22c55e"},
                    {"label": "FCI", "data": fci, "backgroundColor": "#ef4444"},
                    {"label": "FCF", "data": fcf, "backgroundColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True,
                          "title": {"display": True, "text": "R$"}},
                },
                "plugins": {
                    "title": {"display": True, "text": "Fluxos de Caixa Consolidados"},
                },
            },
        },
    }


def _build_dfc_fco_vs_ll_chart(periods: list[dict]) -> dict | None:
    """[v1.25 v4] Build the FCO vs Lucro Líquido line chart (earnings-quality
    divergence) from a list of period dicts. Works for BOTH annual + quarterly
    periods (each period must have a ``metrics`` dict with ``fco`` and
    ``lucro_liquido`` keys).

    Returns None if fewer than 2 periods or all values are None.

    Moved here from ``build_dfc_quality_section`` so the chart switches with
    the period_toggle. The quality TABLE (TTM values) stays in
    ``build_dfc_quality_section`` (point-in-time, not time-series).
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    fco_series, ni_series = [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        fco_series.append(_num_or_none(m.get("fco")))
        ni_series.append(_num_or_none(m.get("lucro_liquido")))
    if not any(v is not None for v in fco_series + ni_series):
        return None
    return {
        "type": "chart",
        "title": "FCO vs Lucro Líquido",
        "description": (
            "Divergência entre FCO (Fluxo de Caixa Operacional) e Lucro "
            "Líquido ao longo do tempo. Quando o Lucro Líquido cresce mas o "
            "FCO cai (ou fica persistentemente abaixo), pode indicar baixa "
            "qualidade dos lucros (accruals agressivos, recebimentos não "
            "realizados)."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "FCO", "data": fco_series,
                     "borderColor": "#22c55e", "fill": False, "tension": 0.3},
                    {"label": "Lucro Líquido", "data": ni_series,
                     "borderColor": "#3b82f6", "fill": False, "tension": 0.3},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$"}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": "Divergência FCO vs Lucro Líquido"},
                },
            },
        },
    }


def _num_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metrics_from_period(p: dict) -> dict:
    """[v1.24] Extract named metrics from a period dict, supporting BOTH the
    annual shape (``metrics`` field pre-computed by annual/quarterly summary
    builders) AND the quarterly-statement shape (``accounts`` dict only — no
    pre-computed metrics, because ``_fetch_all_statements_quarterly`` returns
    raw accounts).

    Used by ``build_statement_trend_chart`` and ``build_dfc_trend_chart`` so
    they can consume either period type transparently.

    Codes extracted (matches ``_extract_metrics`` in fetchers.py):
      - receita_liquida  ← 3.01
      - ebit             ← 3.05
      - da               ← 6.01.01.02 (fallback 6.02.01.02 — direct method)
      - ebitda           ← ebit + da (ebit_only fallback when da missing)
      - lucro_liquido    ← 3.11
      - fco              ← 6.01
      - fci              ← 6.02
      - fcf              ← 6.03
    """
    m = p.get("metrics")
    if m is not None:
        return m
    accounts = p.get("accounts") or {}

    def _v(code: str) -> float | None:
        a = accounts.get(code)
        if a is None:
            return None
        return _num_or_none(a.get("valor_brl"))

    receita = _v("3.01")
    ebit = _v("3.05")
    da = _v("6.01.01.02")
    if da is None:
        da = _v("6.02.01.02")  # DFC_MD direct-method fallback
    ebitda: float | None = None
    if ebit is not None and da is not None:
        ebitda = ebit + da
    elif ebit is not None:
        ebitda = ebit  # ebit_only fallback

    return {
        "receita_liquida": receita,
        "ebit": ebit,
        "ebitda": ebitda,
        "lucro_liquido": _v("3.11"),
        "fco": _v("6.01"),
        "fci": _v("6.02"),
        "fcf": _v("6.03"),
    }


# ── Tab 7: DVA (table + doughnut chart) ──────────────────────────────────────

def build_dva_sections(
    dva_result: dict,
    company: str | None = None,
    dva_result_q: dict | None = None,
) -> list[dict]:
    """Build the DVA tab: generation + distribution table + doughnut chart.

    [v1.24] Quarterly support:
      - Accepts optional ``dva_result_q`` (quarterly DVA statement result).
      - The multi-period table is wrapped in a ``period_toggle`` section so
        the user can switch between annual + quarterly views.
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table.
      - Trend chart now prefers quarterly periods (when available).

    [v1.23 F4] Appends a DVA trend chart (VA Bruta/VA Líquida/Total a
    Distribuir + price overlay on right axis) at the END of the sections.
    Backward-compatible: ``company`` is optional; when None the overlay is
    skipped.
    """
    sections: list[dict] = []

    dva_periods = (dva_result or {}).get("periods") or []
    dva_periods_q = (dva_result_q or {}).get("periods") or []
    if not dva_periods:
        sections.append({
            "type": "text",
            "text": "DVA data unavailable for this company.",
        })
        return sections

    latest = dva_periods[0]
    accounts = latest.get("accounts") or {}
    if not accounts:
        sections.append({
            "type": "text",
            "text": "DVA accounts not found for the latest period.",
        })
        return sections

    # [v1.25 v3] Build annual + quarterly trend charts, pass into period_toggle.
    dva_annual_trend = build_dva_trend_chart(dva_periods, company)
    dva_quarterly_trend = build_dva_trend_chart(dva_periods_q, company) if dva_periods_q else None

    # [v1.24] Multi-period table + charts INSIDE period_toggle.
    sections.extend(_build_period_toggle_sections(
        "DVA", dva_periods, dva_periods_q, "DVA",
        annual_chart=dva_annual_trend,
        quarterly_chart=dva_quarterly_trend,
    ))

    # If neither annual nor quarterly table could be built, fall back to a
    # bare text notice so the tab isn't empty.
    if not sections:
        sections.append({
            "type": "text",
            "text": "DVA multi-period comparison unavailable.",
        })

    # Doughnut chart: wealth distribution.
    # [v1.16 DVA-fix] Two fixes vs the v1.15 builder:
    #
    # 1. NEW TAXONOMY: CVM DVA codes changed in 2012+. The OLD taxonomy
    #    used 8.01 (Pessoal), 8.02 (Governo), 8.03 (Credores), 8.04
    #    (Acionistas). The NEW taxonomy uses 7.08.01 (Pessoal), 7.08.02
    #    (Governo), 7.08.03 (Credores), 7.08.04 (Acionistas — Remuneração
    #    de Capitais Próprios). Most filers post-2012 use the NEW codes;
    #    the old builder only matched "8.0X" prefixes, so all 7.08.*
    #    accounts fell into "Outros". We now match BOTH taxonomies.
    #
    # 2. DOUBLE-COUNT: The old builder summed parent + children codes
    #    (e.g., 7.08.04 + 7.08.04.01 + 7.08.04.02), inflating the
    #    "Acionistas" slice. The new builder uses depth-3 codes ONLY
    #    (7.08.01 / 7.08.02 / 7.08.03 / 7.08.04) for the new taxonomy
    #    and depth-2 codes (8.01 / 8.02 / 8.03 / 8.04) for the old
    #    taxonomy. Deeper codes (7.08.04.01 JCP, 7.08.04.02 Dividendos)
    #    are skipped because they are sub-components of the parent.
    # [v1.16.1 DVA-fix] Two bugs fixed from v1.16:
    #
    # 1. SAME-DEPTH SIBLING DROP: when a filer reports only children
    #    (e.g., 7.08.04.01 JCP + 7.08.04.02 Dividendos) without a parent
    #    (7.08.04 roll-up), the v1.16 dedup kept only the FIRST child
    #    because depth(4) < depth(4) is False. Now: if no depth-3 parent
    #    exists for a prefix, SUM all same-depth children instead of
    #    keeping only one.
    #
    # 2. CROSS-TAXONOMY DOUBLE-COUNT: if a filer reports BOTH new (7.08.04)
    #    AND old (8.04) taxonomies for the same label in the same period,
    #    v1.16 summed both → double-count. Now: prefer the NEW taxonomy
    #    (7.08.*) when both are present; only fall back to old (8.*) when
    #    new is absent for that label.
    distribution_labels = {
        # NEW taxonomy (post-2012) — depth-3 codes under 7.08.*
        "7.08.01": "Pessoal",
        "7.08.02": "Governo",
        "7.08.03": "Credores",
        "7.08.04": "Acionistas",
        "7.08.05": "Outros",
        # OLD taxonomy (pre-2012) — depth-2 codes under 8.*
        "8.01": "Pessoal",
        "8.02": "Governo",
        "8.03": "Credores",
        "8.04": "Acionistas",
    }

    NEW_TAXONOMY_PREFIXES = {"7.08.01", "7.08.02", "7.08.03", "7.08.04", "7.08.05"}

    def _dva_depth(codigo: str) -> int:
        """Number of dot-separated levels in a CVM account code.
        '7.08.04' → 3, '7.08.04.01' → 4, '8.01' → 2."""
        return len(codigo.split("."))

    # Pass 1: collect all distribution-side codes + their depth + matched prefix.
    # dist_rows: (codigo, label, valor, depth, matched_prefix)
    dist_rows: list[tuple[str, str, float, int, str]] = []
    for codigo, acc in accounts.items():
        if (acc.get("section") != "Distribuição"
                or acc.get("valor_brl") is None):
            continue
        label = None
        matched_prefix = None
        for prefix, lbl in distribution_labels.items():
            if codigo == prefix or codigo.startswith(prefix + "."):
                label = lbl
                matched_prefix = prefix
                break
        if label is None:
            continue
        try:
            val = float(acc["valor_brl"])
        except (TypeError, ValueError):
            continue
        dist_rows.append((codigo, label, val, _dva_depth(codigo), matched_prefix))

    # Pass 2: for each prefix, collect ALL values grouped by depth.
    # If a shallow depth exists (parent), use ONLY that (skip children).
    # If no shallow depth exists (only children), SUM all children.
    # best_per_prefix: prefix -> {depth: sum_of_values_at_that_depth}
    per_prefix_by_depth: dict[str, dict[int, float]] = {}
    for codigo, label, val, depth, prefix in dist_rows:
        if prefix not in per_prefix_by_depth:
            per_prefix_by_depth[prefix] = {}
        per_prefix_by_depth[prefix][depth] = per_prefix_by_depth[prefix].get(depth, 0.0) + val

    # For each prefix, pick the shallowest depth's sum.
    best_per_prefix: dict[str, float] = {}
    for prefix, depth_map in per_prefix_by_depth.items():
        shallowest_depth = min(depth_map.keys())
        best_per_prefix[prefix] = depth_map[shallowest_depth]

    # Pass 3: aggregate by label, but prefer NEW taxonomy when both
    # new + old are present for the same label.
    # Group prefixes by label, track which prefixes have new-taxonomy data.
    label_to_prefixes: dict[str, list[str]] = {}
    for prefix, label in distribution_labels.items():
        if prefix in best_per_prefix:
            label_to_prefixes.setdefault(label, []).append(prefix)

    agg: dict[str, float] = {}
    for label, prefixes in label_to_prefixes.items():
        has_new = any(p in NEW_TAXONOMY_PREFIXES for p in prefixes)
        if has_new:
            # Prefer new taxonomy — sum only new-taxonomy prefixes for this label.
            for p in prefixes:
                if p in NEW_TAXONOMY_PREFIXES:
                    agg[label] = agg.get(label, 0.0) + best_per_prefix[p]
        else:
            # Only old taxonomy present — use it.
            for p in prefixes:
                agg[label] = agg.get(label, 0.0) + best_per_prefix[p]

    dist_data = [(label, val) for label, val in agg.items()]

    if dist_data:
        labels = [lbl for lbl, _ in dist_data]
        values = [val for _, val in dist_data]
        # Use absolute values for the chart (DVA distribution is positive).
        abs_values = [abs(v) for v in values]
        sections.append({
            "type": "chart",
            "title": "Distribuição de Riqueza",
            "description": (
                "Distribuição do valor adicionado por stakeholder: Pessoal, "
                "Governo, Credores e Acionistas. Códigos CVM 7.08.01-05 "
                "(nova taxonomia) ou 8.01-04 (antiga)."
            ),
            "chart_data": {
                "type": "doughnut",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": "Distribuição de Riqueza",
                        "data": abs_values,
                        "backgroundColor": [
                            "#22c55e",  # Pessoal
                            "#ef4444",  # Governo
                            "#f59e0b",  # Credores
                            "#3b82f6",  # Acionistas
                            "#a855f7",  # Outros
                        ],
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    # [v1.13 review-fix] Flag consumed by dashboard.html's
                    # chart-rendering script to attach a tooltip callback
                    # showing each slice's percentage of the total.  The
                    # callback is a JS function (not JSON-serializable), so
                    # we set a flag here and the template injects the
                    # callback at render time.
                    "_tooltipPercent": True,
                },
            },
        })

    # [new commit] NEW chart: DVA generation-side decomposition (bar chart).
    # User feedback: "DVA generation-side bar chart showing the wealth
    # creation waterfall: 7.01 Receitas, 7.03 Insumos, 7.04 VA Bruto,
    # 7.05 Retenções, 7.06 VA Líquido, 7.07 VA Recebido, 7.08 Total a
    # Distribuir". Codes are already in `accounts` (DVA mode fetches them).
    gen_chart = _build_dva_generation_chart(accounts, latest)
    if gen_chart is not None:
        sections.append(gen_chart)

    # [v1.25 v3] Trend chart is now INSIDE the period_toggle (above).

    return sections


def _build_dva_generation_chart(accounts: dict, latest_period: dict) -> dict | None:
    """Build the DVA generation-side waterfall bar chart.

    Shows the wealth-creation pipeline: Receitas → (−Insumos) → VA Bruto →
    (−Retenções) → VA Líquido → (+VA Recebido) → Total a Distribuir.

    Codes per user spec (post-2012 CVM DVA taxonomy):
      7.01 Receitas / 7.03 Insumos / 7.04 VA Bruto / 7.05 Retenções /
      7.06 VA Líquido / 7.07 VA Recebido / 7.08 Total a Distribuir.

    Returns None when fewer than 2 of the codes are present (graceful
    degradation when the filer doesn't report a full DVA).
    """
    # (codigo, label) pairs in waterfall order.
    gen_codes = [
        ("7.01", "Receitas"),
        ("7.03", "Insumos"),
        ("7.04", "VA Bruto"),
        ("7.05", "Retenções"),
        ("7.06", "VA Líquido"),
        ("7.07", "VA Recebido"),
        ("7.08", "Total a Distribuir"),
    ]
    labels: list[str] = []
    values: list[float] = []
    for code, label in gen_codes:
        acc = accounts.get(code) or {}
        v = acc.get("valor_brl")
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        labels.append(f"{code} — {label}")
        values.append(fv)
    if len(labels) < 2:
        return None
    period_label = (latest_period or {}).get("period") \
        or (latest_period or {}).get("data_fim_exerc") or "Latest"
    return {
        "type": "chart",
        "title": f"Geração de Riqueza — {period_label}",
        "description": (
            "Cascata de geração de valor adicionado: Receitas → Insumos → "
            "VA Bruto → Retenções → VA Líquido → VA Recebido → Total a "
            "Distribuir. Códigos CVM 7.01-7.08 (nova taxonomia)."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Geração de Riqueza (R$)",
                    "data": values,
                    "backgroundColor": "#0d9488",
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$"}},
                    "x": {"ticks": {"maxRotation": 45, "minRotation": 30}},
                },
                "plugins": {
                    "title": {"display": True, "text": "DVA — Geração de Valor Adicionado"},
                },
            },
        },
    }


# ── Error-section helper (used by dashboard for failed sub-mode calls) ───────

def build_error_section(stage: str, error: str) -> dict:
    """Build a `type: "text"` section describing a failed sub-mode call."""
    return {
        "type": "text",
        "text": (
            f"{stage} indisponível para esta empresa. "
            f"Detalhe: {error}"
        ),
    }


# ── [new commit] F12: DFC quality analysis ───────────────────────────────────

def _safe_engine_call(fn, *args, **kwargs) -> float | None:
    """Call a calculations engine fn; return its float result or None on failure.

    Used by build_dfc_quality_section / build_dividend_sustainability_section
    to gracefully degrade when the DFC or DVA DB is missing — engine calls
    raise FileNotFoundError etc., which we swallow so a single missing
    statement doesn't crash the whole dashboard tab.
    """
    try:
        v = fn(*args, **kwargs)
    except Exception:
        return None
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_dfc_quality_section(
    latest_annual_period: dict | None,
    annual_periods: list[dict],
    company: str,
    today: str,
) -> list[dict]:
    """[new commit] F12 — DFC quality analysis (appended to DFC tab).

    Shows:
      - Table: FCO, FCI, FCF (financing), FCF_true = FCO - |CapEx| for the
        latest annual period. NOTE: the financials ``metrics`` dict uses
        "fcf" for FINANCING cash flow (DFC 6.03 — Fluxo de Caixa de
        Financiamento), NOT Free Cash Flow. FCF_true uses a separate key
        to avoid that collision.
      - Cash Conversion Ratio = FCO / Lucro Líquido (TTM).

    [v1.25 v4] The 5Y "FCO vs Lucro Líquido" line chart was MOVED to
    ``build_dfc_sections`` so it lives inside the period_toggle (annual +
    quarterly versions switch with the toggle). This function now returns
    ONLY the quality TABLE (point-in-time TTM values) — not a time-series.
    ``annual_periods`` is kept in the signature for backward compatibility
    with existing callers (e.g. dashboard.py) but is no longer used to
    build a chart here.

    Args:
        latest_annual_period: latest annual period dict (or None).
        annual_periods: list of all annual period dicts (UNUSED since
            v1.25 v4 — kept for backward compat).
        company: ticker/CNPJ — needed for capex_at + ttm_earnings_at calls.
        today: YYYY-MM-DD for the TTM engine anchoring.
    """
    sections: list[dict] = []

    # Engine-backed TTM values (capex + earnings) — best-effort, None on fail.
    from skills.cvm.calculations.engines.dfc.capex import capex_at
    from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
    from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at

    capex_ttm = _safe_engine_call(capex_at, company, today)
    fco_ttm = _safe_engine_call(operating_cf_at, company, today)
    ni_ttm = _safe_engine_call(ttm_earnings_at, company, today)

    # Latest annual FCO/FCI/FCF (financing) — from the metrics dict.
    fco_annual = fci_annual = fcf_financing_annual = None
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        fco_annual = _num_or_none(m.get("fco"))
        fci_annual = _num_or_none(m.get("fci"))
        fcf_financing_annual = _num_or_none(m.get("fcf"))

    # FCF_true = FCO - |CapEx|. Capex from capex_at is negative (outflow),
    # so we take abs then subtract from FCO. Use TTM values when available;
    # fall back to latest annual FCO if TTM engine failed.
    fco_for_fcf = fco_ttm if fco_ttm is not None else fco_annual
    fcf_true: float | None = None
    if fco_for_fcf is not None and capex_ttm is not None:
        fcf_true = fco_for_fcf - abs(capex_ttm)

    # Cash Conversion Ratio = FCO / Lucro Líquido (TTM preferred).
    cash_conversion: float | None = None
    if fco_ttm is not None and ni_ttm is not None and ni_ttm != 0:
        cash_conversion = fco_ttm / ni_ttm
    elif fco_annual is not None:
        # Fall back to latest annual NI.
        if latest_annual_period:
            ni_annual = _num_or_none(
                (latest_annual_period.get("metrics") or {}).get("lucro_liquido"))
            if ni_annual and ni_annual != 0:
                cash_conversion = fco_annual / ni_annual

    # Table: FCO, FCI, FCF (financing), FCF_true, Cash Conversion.
    # [v1.25 v2] Tooltips on metric name (1st column).
    rows = [
        [{"text": "FCO (Anual)", "tooltip": "Fluxo de Caixa Operacional = DFC 6.01 (anual)"}, _fmt(fco_annual, "brl")],
        [{"text": "FCI (Anual)", "tooltip": "Fluxo de Caixa de Investimento = DFC 6.02 (anual)"}, _fmt(fci_annual, "brl")],
        [{"text": "FCF — Financiamento (Anual)", "tooltip": "Fluxo de Caixa de Financiamento = DFC 6.03 (anual). NÃO é Free Cash Flow."}, _fmt(fcf_financing_annual, "brl")],
        [{"text": "FCO (TTM)", "tooltip": "Fluxo de Caixa Operacional TTM (últimos 12 meses)"}, _fmt(fco_ttm, "brl")],
        [{"text": "CapEx (TTM)", "tooltip": "Capital Expenditure TTM = aquisição de imobilizado/intangível (DFC)"}, _fmt(capex_ttm, "brl")],
        [{"text": "FCF Verdadeiro = FCO − |CapEx| (TTM)", "tooltip": "Free Cash Flow = FCO − |CapEx|. Caixa livre após manutenção do negócio."}, _fmt(fcf_true, "brl")],
        [{"text": "Lucro Líquido (TTM)", "tooltip": "Lucro Líquido TTM = DRE 3.09 (últimos 12 meses)"}, _fmt(ni_ttm, "brl")],
        [{"text": "Cash Conversion = FCO / LL", "tooltip": "Cash Conversion Ratio = FCO / Lucro Líquido. >1 = alta qualidade (caixa > lucro)."}, _fmt(cash_conversion, "num")],
    ]
    sections.append({
        "title": "Qualidade do Fluxo de Caixa",
        "description": (
            "FCF Verdadeiro = FCO − |CapEx| (capex é saída de caixa, "
            "por isso subtrai-se o valor absoluto). Cash Conversion Ratio "
            "= FCO / Lucro Líquido — abaixo de 0.8 pode indicar baixa "
            "conversão de lucro em caixa (red flag de qualidade)."
        ),
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
        "note": (
            "Atenção: no Dashboard BR, 'FCF' é o Fluxo de Caixa de "
            "Financiamento (DFC 6.03), NÃO Free Cash Flow. Use a linha "
            "'FCF Verdadeiro' para o Free Cash Flow real."
        ),
    })

    # [v1.25 v4] The 5Y "FCO vs Lucro Líquido" line chart was MOVED to
    # ``build_dfc_sections`` so it lives inside the period_toggle (annual +
    # quarterly versions). The quality TABLE above (TTM values) STAYS here
    # — it's point-in-time, not a time-series. ``annual_periods`` is kept
    # in the signature for backward compatibility with existing callers
    # (e.g. dashboard.py) but is no longer used to build a chart here.

    return sections


# ── [new commit] F13: Dividend sustainability ────────────────────────────────

def build_dividend_sustainability_section(
    ratios_payload: dict,
    latest_annual_period: dict | None,
    company: str,
    today: str,
) -> list[dict]:
    """[new commit] F13 — Dividend sustainability (appended to DVA tab).

    Shows:
      - Payout ratio (from ratios_payload, computed as dividends / NI).
      - Dividend Coverage = Lucro Líquido / Dividends Paid.
      - 5Y dividend trend chart (BRL total, from dividends_paid_periods).

    Args:
        ratios_payload: dict from compute_all_ratios. May contain "payout"
            when the dpa metric isn't excluded (currently dashboard.py
            excludes ["lpa", "vpa", "dpa", "rps"] — payout is an alias of
            dpa, so it's also excluded; we fall back to computing payout
            from latest_annual_period["ratios"]["payout"]).
        latest_annual_period: latest annual period dict (or None).
        company: ticker/CNPJ — needed for dividends_paid_at + ttm_earnings_at.
        today: YYYY-MM-DD for TTM anchoring.
    """
    sections: list[dict] = []

    from skills.cvm.calculations.engines.dva.dividends_paid import (
        dividends_paid_at, dividends_paid_periods)
    from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at

    # Payout: prefer ratios_payload, then latest_annual_period.ratios.payout.
    payout = ratios_payload.get("payout")
    if payout is None and latest_annual_period:
        payout = (latest_annual_period.get("ratios") or {}).get("payout")
    payout = _num_or_none(payout)

    # TTM dividends paid (BRL total) + TTM net income.
    div_ttm = _safe_engine_call(dividends_paid_at, company, today)
    ni_ttm = _safe_engine_call(ttm_earnings_at, company, today)

    # Dividend Coverage = NI / |Dividends Paid|. Dividends are negative
    # outflow in the DVA engine (matches capex convention); take abs.
    div_coverage: float | None = None
    if ni_ttm is not None and div_ttm is not None and div_ttm != 0:
        div_coverage = ni_ttm / abs(div_ttm)

    # [v1.25 v2] Tooltips on metric name (1st column).
    rows = [
        [{"text": "Payout Ratio (LL → Dividendos)", "tooltip": "Payout = Dividendos / Lucro Líquido. % do lucro distribuído aos acionistas."}, _fmt(payout, "pct")],
        [{"text": "Dividendos Pagos (TTM, BRL)", "tooltip": "Dividendos pagos TTM = DVA 7.08.04 (Remuneração de Capital Próprio). Valor negativo (saída)."}, _fmt(div_ttm, "brl")],
        [{"text": "Lucro Líquido (TTM, BRL)", "tooltip": "Lucro Líquido TTM = DRE 3.09 (últimos 12 meses)"}, _fmt(ni_ttm, "brl")],
        [{"text": "Cobertura de Dividendos = LL / Div", "tooltip": "Cobertura = Lucro Líquido / Dividendos. <1.5x = risco de corte. >2x = saudável."}, _fmt(div_coverage, "num")],
    ]
    sections.append({
        "title": "Sustentabilidade de Dividendos",
        "description": (
            "Payout Ratio = Dividendos / Lucro Líquido. Cobertura de "
            "Dividendos = Lucro Líquido / Dividendos — abaixo de 1.5x "
            "indica risco de cortes em cenários de queda de lucro. Acima "
            "de 2x é considerado saudável."
        ),
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
        "note": (
            "Dividendos Pagos vem do DVA 7.08.04 (Remuneração de Capitais "
            "Próprios) — é o valor agregado reportado pela empresa, não o "
            "por-ação da B3."
        ),
    })

    # 5Y dividend trend chart from dividends_paid_periods.
    div_periods = _safe_engine_call(dividends_paid_periods, company)
    if isinstance(div_periods, list) and len(div_periods) >= 2:
        labels = [str(p.get("date", ""))[:10] for p in div_periods]
        values = []
        for p in div_periods:
            v = p.get("ttm_dividends_paid")
            values.append(_num_or_none(v))
        if any(v is not None for v in values):
            sections.append({
                "type": "chart",
                "title": "Dividendos Pagos — TTM ao longo do tempo",
                "description": (
                    "Série histórica de dividendos pagos (TTM, BRL) — "
                    "agregado reportado no DVA 7.08.04. Mostra a "
                    "trajetória da distribuição de capital aos acionistas."
                ),
                "chart_data": {
                    "type": "line",
                    "data": {
                        "labels": labels,
                        "datasets": [{
                            "label": "Dividendos Pagos (TTM)",
                            "data": values,
                            "borderColor": "#a855f7",
                            "backgroundColor": "#a855f7",
                            "fill": False,
                            "tension": 0.3,
                        }],
                    },
                    "options": {
                        "responsive": True,
                        "maintainAspectRatio": False,
                        "scales": {
                            "y": {"ticks": {},
                                  "title": {"display": True, "text": "R$ (TTM)"}},
                        },
                        "plugins": {
                            "title": {"display": True,
                                      "text": "Evolução dos Dividendos Pagos"},
                        },
                    },
                },
            })

    return sections


# ── [new commit] F14: Accounting red flags ───────────────────────────────────

def build_red_flags_section(
    bpa_result: dict,
    bpp_result: dict,
    dre_result: dict,
    dfc_result: dict,
    dva_result: dict,
    annual_periods: list[dict],
) -> dict:
    """[new commit] F14 — Accounting red flags (appended to Overview tab).

    Surfaces the cross-statement consistency checks already implemented in
    ``skills/cvm/financials/validation.py`` (BPA 1 ≈ 1.01+1.02; DRE
    3.03 ≈ 3.01-3.02; BPP 2 ≈ 2.01+2.02+2.03; DVA 7.08 ≈ Σ7.08.0x). Each
    statement's periods are checked; mismatches beyond the 5% tolerance
    surface as warnings.

    Also runs two extra checks (computed here, not in validation.py):
      - ROE with negative PL (silent None in metrics.py — flagged here).
      - FCO declining 3Y (earnings-quality red flag).

    Args:
        bpa_result, bpp_result, dre_result, dfc_result, dva_result:
            statement-mode results (each with ``periods`` list).
        annual_periods: list of annual period dicts (for FCO trend check).

    Returns:
        A ``type: "table"`` section with one row per check (pass/fail).
    """
    from skills.cvm.financials.validation import (
        validate_statement_consistency,
    )

    rows: list[list[str]] = []

    def _add_check(label: str, warnings: list[str]) -> None:
        if not warnings:
            rows.append([label, "✓ OK", "—"])
        else:
            # Truncate to first warning for compactness (full text in
            # collapsible below if needed).
            summary = "; ".join(warnings)
            if len(summary) > 220:
                summary = summary[:217] + "..."
            rows.append([label, "⚠ Divergência", summary])

    # Statement consistency checks (validation.py).
    for stmt_result, stmt_type, label in [
        (bpa_result, "bpa", "BPA: 1 = 1.01 + 1.02"),
        (bpp_result, "bpp", "BPP: 2 = 2.01 + 2.02 + 2.03"),
        (dre_result, "dre", "DRE: 3.03 = 3.01 − 3.02"),
        (dva_result, "dva", "DVA: 7.08 = Σ(7.08.01-04)"),
    ]:
        if not isinstance(stmt_result, dict):
            continue
        if stmt_result.get("status") != "ok":
            continue
        periods = stmt_result.get("periods") or []
        warnings = validate_statement_consistency(periods, stmt_type)
        _add_check(label, warnings)

    # Extra check 1: ROE with negative PL.
    pl_warnings: list[str] = []
    if annual_periods:
        for p in annual_periods[:3]:  # latest 3 annual periods
            m = p.get("metrics") or {}
            pl = _num_or_none(m.get("patrimonio_liquido"))
            if pl is not None and pl < 0:
                pl_warnings.append(
                    f"{p.get('period', '?')}: PL negativo "
                    f"({pl:,.0f}) — ROE não é significativo."
                )
    _add_check("ROE: PL positivo (3 últimos anos)", pl_warnings)

    # Extra check 2: FCO declining 3Y (earnings-quality red flag).
    fco_warnings: list[str] = []
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) >= 3:
        # Take last 3 periods (chronological), check FCO trend.
        last3 = sorted_periods[-3:]
        fco_vals = []
        for p in last3:
            m = p.get("metrics") or {}
            fco_vals.append(_num_or_none(m.get("fco")))
        if all(v is not None for v in fco_vals):
            # Flag if FCO strictly declined across all 3 periods.
            if fco_vals[0] > fco_vals[1] > fco_vals[2]:
                fco_warnings.append(
                    f"FCO caiu 3 anos consecutivos: "
                    f"{fco_vals[0]:,.0f} → {fco_vals[1]:,.0f} → "
                    f"{fco_vals[2]:,.0f}. Red flag de qualidade dos lucros."
                )
    _add_check("FCO: tendência 3 anos (não-declínio)", fco_warnings)

    # If no checks ran at all (all statements failed), show empty message.
    if not rows:
        return {
            "type": "collapsible",
            "title": "Red Flags Contábeis",
            "text": "Nenhum dado contábil disponível para validação.",
            "open": False,
        }

    has_warnings = any("⚠" in r[1] for r in rows)
    return {
        "type": "collapsible",
        "title": f"Red Flags Contábeis ({'atenção' if has_warnings else 'OK'})",
        "open": has_warnings,
        "sections": [{
            "title": "Verificações de Consistência Contábil",
            "description": (
                "Cada verificação compara identidades contábeis (e.g., "
                "Ativo = Circulante + Não Circulante) com tolerância de "
                "5%. Divergências podem indicar erro de extração, "
                "arredondamento ou troca de taxonomia (CVM 2012+)."
            ),
            "type": "table",
            "columns": ["Verificação", "Status", "Detalhe"],
            "rows": rows,
        }],
    }


# ── TTM chart builder (v1.15) ────────────────────────────────────────────────

def build_ttm_chart(ttm_periods: list[dict]) -> dict | None:
    """Build a line chart showing TTM Revenue + EBITDA + Net Income over time.

    Args:
        ttm_periods: list of TTM period dicts (from ttm() mode) with
                     "quarter" and "metrics" keys.

    Returns None if no valid data.
    """
    labels = []
    revenue = []
    ebitda = []
    net_income = []
    for p in ttm_periods:
        m = p.get("metrics") or {}
        rev = m.get("receita_liquida")
        ebd = m.get("ebitda")
        ni = m.get("lucro_liquido")
        if rev is None and ebd is None and ni is None:
            continue
        labels.append(p.get("quarter", ""))
        revenue.append(_num_or_none(rev))
        ebitda.append(_num_or_none(ebd))
        net_income.append(_num_or_none(ni))

    if not labels:
        return None

    return {
        "type": "chart",
        "title": "Série Temporal Anualizada (TTM)",
        "description": (
            "Receita, EBITDA e Lucro Líquido trailing-12-months (TTM) "
            "recomputados a cada trimestre. Dessaonaliza os dados "
            "trimestrais e mostra a tendência real."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita (TTM)", "data": revenue,
                     "borderColor": "#0d9488", "fill": False, "tension": 0.3},
                    {"label": "EBITDA (TTM)", "data": ebitda,
                     "borderColor": "#f59e0b", "fill": False, "tension": 0.3},
                    {"label": "Lucro Líq. (TTM)", "data": net_income,
                     "borderColor": "#3b82f6", "fill": False, "tension": 0.3},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                  "title": {"display": True, "text": "R$ (TTM)"}}},
                "plugins": {
                    "title": {"display": True, "text": "Série Temporal TTM (Anualizada)"},
                },
            },
        },
    }


def build_ttm_table(ttm_periods: list[dict]) -> dict:
    """Build a table showing TTM metrics per period.

    Columns: Período, Receita, EBITDA, Lucro Líquido, Marg. EBITDA, Marg. Líq.
    """
    columns = ["Período", "Receita (TTM)", "EBITDA", "Lucro Líq.",
               "Marg. EBITDA", "Marg. Líq."]
    rows = []
    for p in ttm_periods:
        m = p.get("metrics") or {}
        r = p.get("ratios") or {}
        rows.append([
            p.get("quarter", ""),
            _fmt(m.get("receita_liquida"), "brl"),
            _fmt(m.get("ebitda"), "brl"),
            _fmt(m.get("lucro_liquido"), "brl"),
            _fmt(r.get("marg_ebitda"), "pct"),
            _fmt(r.get("marg_liquida"), "pct"),
        ])
    return {
        "title": "Rolling TTM (Anualizado)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "note": "Trailing 12 months recomputed at each quarter boundary. Deseasonalized.",
    }


# ── YoY Quarterly chart builder (v1.15) ──────────────────────────────────────

def build_yoy_chart(groups: list[dict]) -> dict | None:
    """Build a bar chart showing Revenue YoY growth per quarter group.

    One dataset per quarter (Q1, Q2, Q3, Q4), x-axis = years.
    Shows whether each quarter is growing or shrinking YoY.

    Args:
        groups: list of group dicts (from yoy_quarterly() mode) with
                "quarter" and "periods" keys.

    Returns None if no valid data.
    """
    datasets = []
    all_years: set[int] = set()

    for g in groups:
        q_label = g.get("quarter", "")
        periods = g.get("periods") or []
        if not periods:
            continue

        # [new commit] F16 fix: build year→growth dict so datasets align
        # with the global labels list. Was appending growths sequentially,
        # which misaligned when groups had different year coverage (e.g.,
        # Q1 has 4 years, Q2 has 3 — Q2's data plotted at wrong labels).
        year_to_growth: dict[int, float | None] = {}
        for p in periods:
            year = p.get("year")
            yoy = p.get("yoy_growth") or {}
            growth = yoy.get("receita_liquida")
            if year is not None:
                all_years.add(year)
                year_to_growth[year] = (
                    _num_or_none(growth) * 100 if growth is not None else None
                )

        if year_to_growth:
            datasets.append({
                "label": q_label,
                "data": year_to_growth,  # dict — will be aligned below
            })

    if not datasets:
        return None

    labels = sorted(str(y) for y in all_years)

    # [new commit] Align each dataset with the global labels list.
    # Convert year→growth dicts to ordered lists matching `labels`.
    for ds in datasets:
        year_to_growth = ds.pop("data")
        ds["data"] = [
            year_to_growth.get(int(yr)) for yr in labels
        ]

    return {
        "type": "chart",
        "title": "Crescimento YoY por Trimestre",
        "description": (
            "Crescimento YoY (year-over-year) da Receita Líquida por "
            "trimestre (Q1/Q2/Q3/Q4) ao longo dos anos. Mostra se cada "
            "trimestre está crescendo ou encolhendo em relação ao mesmo "
            "trimestre do ano anterior."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "Crescimento YoY (%)"}}},
                "plugins": {
                    "title": {"display": True, "text": "Crescimento YoY da Receita por Trimestre"},
                },
            },
        },
    }


def build_yoy_table(groups: list[dict]) -> list[dict]:
    """Build per-quarter tables showing YoY comparison across years.

    [new commit] MAJOR REWRITE — now groups by QUARTER (was by year).
    User feedback: "its grouped by year, should be by quarter, to see the
    differences of 4t26 and 4t25 and so on". Each quarter (Q1/Q2/Q3/Q4)
    gets its own table showing all available years for that quarter,
    newest year first. This lets you compare 4T2026 vs 4T2025 vs 4T2024
    directly.

    Returns a list of section dicts (one per quarter), in Q4→Q1 order.
    """
    columns = ["Ano", "Receita", "EBITDA", "Lucro Líq.", "Receita YoY %"]

    # Flatten all periods across groups, collect by quarter number.
    by_quarter: dict[int, list[dict]] = {}
    quarter_labels: dict[int, str] = {}
    for g in groups:
        q_label = g.get("quarter", "")
        for p in g.get("periods") or []:
            year = p.get("year")
            qnum = p.get("quarter", 0)
            if year is None:
                continue
            by_quarter.setdefault(qnum, []).append({
                "year": year,
                "quarter": q_label,
                "receita": (p.get("metrics") or {}).get("receita_liquida"),
                "ebitda": (p.get("metrics") or {}).get("ebitda"),
                "lucro": (p.get("metrics") or {}).get("lucro_liquido"),
                "yoy": (p.get("yoy_growth") or {}).get("receita_liquida"),
            })
            quarter_labels[qnum] = q_label

    sections: list[dict] = []
    # Q4 first (most relevant for full-year comparison), then Q3, Q2, Q1
    for qnum in sorted(by_quarter.keys(), reverse=True):
        periods = sorted(by_quarter[qnum], key=lambda x: x["year"], reverse=True)
        rows = []
        for p in periods:
            rows.append([
                str(p["year"]),
                _fmt(p["receita"], "brl"),
                _fmt(p["ebitda"], "brl"),
                _fmt(p["lucro"], "brl"),
                _fmt(p["yoy"], "pct"),
            ])
        q_label = quarter_labels.get(qnum, f"Q{qnum}")
        sections.append({
            "title": f"{q_label} — YoY por Ano",
            "description": (
                f"Comparação year-over-year do {q_label}. "
                "YoY % = (atual - ano anterior) / |ano anterior|. "
                "Mostra a evolução deste trimestre específico ao longo dos anos."
            ),
            "type": "table",
            "columns": columns,
            "rows": rows,
        })

    if not sections:
        return [{
            "title": "Comparação YoY por Trimestre",
            "type": "text",
            "text": "Sem dados trimestrais disponíveis.",
        }]

    return sections


# ── Period table builder (v1.16) ────────────────────────────────────────────

def build_period_table(periods: list[dict], label: str) -> dict:
    """Build a table showing key metrics across multiple periods.

    Used by the Anual and Trimestral tabs to show raw period data.
    Columns: Período, Receita, EBIT, EBITDA, Lucro Líq., Marg. EBITDA, Marg. Líq.
    """
    columns = ["Período", "Receita", "EBIT", "EBITDA", "Lucro Líq.",
               "Marg. EBITDA", "Marg. Líq."]
    rows = []
    for p in periods:
        m = p.get("metrics") or {}
        r = p.get("ratios") or {}
        rows.append([
            p.get("period", "—"),
            _fmt(m.get("receita_liquida"), "brl"),
            _fmt(m.get("ebit"), "brl"),
            _fmt(m.get("ebitda"), "brl"),
            _fmt(m.get("lucro_liquido"), "brl"),
            _fmt(r.get("marg_ebitda"), "pct"),
            _fmt(r.get("marg_liquida"), "pct"),
        ])
    return {
        "title": f"{label} — {len(rows)} períodos",
        "type": "table",
        "columns": columns,
        "rows": rows,
    }


# ── New chart builders (v1.16) ────────────────────────────────────────────────

def _fetch_year_end_prices(company: str, year_labels: list[str]) -> list[float | None]:
    """Fetch Dec-31 (or closest prior trading day) close price for each year label.

    [v1.23 F2] Used by Overview/DFC/DVA trend charts to add a price overlay
    on a secondary right-axis. Returns a list aligned with ``year_labels``
    (None entries when price data is missing or fetch fails).

    Args:
        company: B3 ticker (e.g. "PETR4").
        year_labels: list of year strings (e.g. ["2020", "2021", "2022"]).
    """
    if not company or not year_labels:
        return [None] * len(year_labels)
    try:
        from skills.cvm.calculations.engines.price import price_series
    except Exception:
        return [None] * len(year_labels)
    # Single fetch for the full year range — much cheaper than N round-trips.
    first_year = min(year_labels)
    last_year = max(year_labels)
    date_from = f"{first_year}-01-01"
    date_to = f"{last_year}-12-31"
    try:
        series = price_series(company, date_from, date_to)
    except Exception:
        series = []
    if not series:
        return [None] * len(year_labels)
    # Index by year (YYYY). Prefer the latest available date <= Dec-31 of that
    # year; price_series already filters refdate within [date_from, date_to]
    # and returns oldest-first. Take the last entry of each year.
    by_year: dict[str, float] = {}
    for point in series:
        d = point.get("date") or ""
        if len(d) >= 4:
            by_year[d[:4]] = float(point.get("close"))
    return [by_year.get(y) for y in year_labels]


def build_overview_trend_chart(
    annual_periods: list[dict], company: str | None = None,
) -> dict | None:
    """Build a multi-line chart showing Receita/EBITDA/Lucro Líq. over annual periods.

    [v1.16] New chart for the Overview tab — gives users an immediate
    visual sense of the company's revenue + earnings trajectory without
    having to navigate to the DRE or Anual tabs.

    [v1.23 F2] Now accepts an optional ``company`` parameter; when provided,
    a 4th dataset (year-end closing price) is added on a secondary right
    Y-axis so users can compare fundamentals with share-price trajectory.
    """
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) < 2:
        return None

    labels = [str(p.get("period")) for p in sorted_periods]
    revenue, ebitda, net_income = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        revenue.append(_num_or_none(m.get("receita_liquida")))
        ebitda.append(_num_or_none(m.get("ebitda")))
        net_income.append(_num_or_none(m.get("lucro_liquido")))

    if not any(v is not None for v in revenue + ebitda + net_income):
        return None

    datasets = [
        {"label": "Receita Líquida", "data": revenue,
         "borderColor": "#0d9488", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "EBITDA", "data": ebitda,
         "borderColor": "#f59e0b", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "Lucro Líquido", "data": net_income,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]

    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }

    # [v1.23 F2] Price overlay on right Y-axis (purple dashed line).
    if company:
        price_series_data = _fetch_year_end_prices(company, labels)
        if any(v is not None for v in price_series_data):
            datasets.append({
                "label": "Preço (R$)",
                "data": price_series_data,
                "borderColor": "#a855f7",
                "backgroundColor": "#a855f7",
                "borderDash": [5, 5],
                "fill": False,
                "tension": 0.3,
                "yAxisID": "y1",
                "pointRadius": 3,
            })
            scales["y1"] = {
                "type": "linear", "position": "right",
                "grid": {"drawOnChartArea": False},
                "ticks": {},
                "title": {"display": True, "text": "Preço (R$)"},
            }

    return {
        "type": "chart",
        "title": "Trajetória de Receita e Lucro (Anual)",
        "description": (
            "Receita Líquida, EBITDA e Lucro Líquido anuais. Mostra a "
            "trajetória de crescimento e rentabilidade da empresa."
            + (" Linha roxa tracejada = preço de fechamento em 31/Dez (eixo direito)."
               if company and "y1" in scales else "")
        ),
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True, "text": "Receita, EBITDA e Lucro Líquido"},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels": [f"{l}-12-31" for l in labels],
        "price_full_datasets": [
            {"data": revenue},
            {"data": ebitda},
            {"data": net_income},
        ],
        "price_full_data": revenue,
    }


def _attach_price_overlay(
    datasets: list[dict], scales: dict, company: str | None, labels: list[str],
) -> bool:
    """[v1.23 F4] Append a year-end price dataset + right-axis scale.

    Mutates ``datasets`` and ``scales`` in place. Returns True when an
    overlay was added (caller can use this to amend the description).
    """
    if not company or not labels:
        return False
    prices = _fetch_year_end_prices(company, labels)
    if not any(v is not None for v in prices):
        return False
    datasets.append({
        "label": "Preço (R$)",
        "data": prices,
        "borderColor": "#a855f7",
        "backgroundColor": "#a855f7",
        "borderDash": [5, 5],
        "fill": False,
        "tension": 0.3,
        "yAxisID": "y1",
        "pointRadius": 3,
    })
    scales["y1"] = {
        "type": "linear", "position": "right",
        "grid": {"drawOnChartArea": False},
        "ticks": {},
        "title": {"display": True, "text": "Preço (R$)"},
    }
    return True


def _period_sort_key(p: dict) -> tuple:
    """[v1.25 v3] Chronological sort key for period dicts.

    Parses ``data_fim_exerc`` date (YYYY-MM-DD) to extract year + quarter.
    Quarterly: (year, quarter) — 4T2025 < 1T2026. Annual: (year, 0).
    Falls back to parsing period label ("2T2026" → (2026, 2)) or string sort.
    """
    # Try year/quarter fields first
    year = p.get("year")
    quarter = p.get("quarter")
    if year is not None:
        return (int(year), int(quarter) if quarter is not None else 0)

    # [v1.25 v3] Parse data_fim_exerc date — this is the reliable field
    date_str = p.get("data_fim_exerc") or ""
    if date_str and len(date_str) >= 7:
        try:
            y = int(date_str[:4])
            m = int(date_str[5:7])
            q = {3: 1, 6: 2, 9: 3, 12: 4}.get(m, 0)
            return (y, q)
        except (ValueError, IndexError):
            pass

    # Parse period label ("2T2026" → (2026, 2), "2025" → (2025, 0))
    period_label = str(p.get("period") or "")
    if period_label:
        # Quarterly: "2T2026"
        if "T" in period_label:
            parts = period_label.split("T")
            if len(parts) == 2:
                try:
                    return (int(parts[1]), int(parts[0]))
                except ValueError:
                    pass
        # Annual: "2025"
        try:
            return (int(period_label), 0)
        except ValueError:
            pass

    return (0, 0, period_label)


def build_statement_trend_chart(
    periods: list[dict], company: str | None, label: str,
) -> dict | None:
    """[v1.23 F4 / v1.24] Receita/EBITDA/Lucro Líq. trend chart with optional price overlay.

    Used by the DRE tab (income-statement metrics). Same concept as the
    Overview trend chart, but accepts a custom ``label`` so the same builder
    can be reused by future tabs.

    [v1.24] Now accepts BOTH annual + quarterly periods (quarterly preferred
    by callers when available). Uses ``_metrics_from_period`` so quarterly
    periods (which only have ``accounts``, no pre-computed ``metrics``) work
    transparently. Sort key upgraded to ``_period_sort_key`` so quarterly
    labels like "4T2025" + "1T2026" sort chronologically (alphabetical sort
    would put "1T2026" before "4T2025" — wrong).

    Args:
        periods: annual OR quarterly period dicts.
        company: B3 ticker for the price overlay; None skips the overlay.
        label: chart title suffix (e.g. "DRE").
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    revenue, ebitda, net_income = [], [], []
    for p in sorted_periods:
        m = _metrics_from_period(p)
        revenue.append(_num_or_none(m.get("receita_liquida")))
        ebitda.append(_num_or_none(m.get("ebitda")))
        net_income.append(_num_or_none(m.get("lucro_liquido")))
    if not any(v is not None for v in revenue + ebitda + net_income):
        return None

    datasets = [
        {"label": "Receita Líquida", "data": revenue,
         "borderColor": "#0d9488", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "EBITDA", "data": ebitda,
         "borderColor": "#f59e0b", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "Lucro Líquido", "data": net_income,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]
    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }
    has_overlay = _attach_price_overlay(datasets, scales, company, labels)
    description = (
        f"Receita Líquida, EBITDA e Lucro Líquido ({label}). "
        "Trajetória de crescimento e rentabilidade."
    )
    if has_overlay:
        description += (
            " Linha roxa tracejada = preço de fechamento de fim de período (eixo direito)."
        )
    return {
        "type": "chart",
        "title": f"Trajetória de Receita e Lucro — {label}",
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True,
                              "text": f"Receita, EBITDA e Lucro — {label}"},
                },
            },
        },
    }


def build_dfc_trend_chart(
    periods: list[dict], company: str | None,
) -> dict | None:
    """[v1.23 F4 / v1.24] FCO/FCI/FCF trend chart with optional price overlay.

    Used by the DFC tab. Plots the 3 DFC sub-totals across periods.

    [v1.24] Now accepts BOTH annual + quarterly periods. Uses
    ``_metrics_from_period`` for quarterly support. Sort key upgraded to
    ``_period_sort_key`` for chronological quarterly ordering.

    Args:
        periods: annual OR quarterly period dicts.
        company: B3 ticker for the price overlay; None skips the overlay.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    fco, fci, fcf = [], [], []
    for p in sorted_periods:
        m = _metrics_from_period(p)
        fco.append(_num_or_none(m.get("fco")))
        fci.append(_num_or_none(m.get("fci")))
        fcf.append(_num_or_none(m.get("fcf")))
    if not any(v is not None for v in fco + fci + fcf):
        return None

    datasets = [
        {"label": "FCO", "data": fco,
         "borderColor": "#22c55e", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "FCI", "data": fci,
         "borderColor": "#ef4444", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "FCF", "data": fcf,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]
    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }
    has_overlay = _attach_price_overlay(datasets, scales, company, labels)
    description = (
        "Fluxos de Caixa Operacional (FCO), de Investimento (FCI) e de "
        "Financiamento (FCF)."
    )
    if has_overlay:
        description += (
            " Linha roxa tracejada = preço de fechamento de fim de período (eixo direito)."
        )
    return {
        "type": "chart",
        "title": "Trajetória dos Fluxos de Caixa",
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True, "text": "FCO, FCI e FCF por Período"},
                },
            },
        },
    }


def build_dva_trend_chart(
    periods: list[dict], company: str | None,
) -> dict | None:
    """[v1.23 F4 / v1.24] VA Bruta/VA Líquida/Total a Distribuir trend chart with overlay.

    Used by the DVA tab. Reads DVA account codes:
      - 7.04 → VA Bruto
      - 7.06 → VA Líquido
      - 7.08 → Total a Distribuir

    [v1.24] Sort key upgraded to ``_period_sort_key`` for chronological
    quarterly ordering. Reads from ``accounts`` dict (works for both annual
    + quarterly — both have ``accounts`` post-reshape).

    Args:
        periods: DVA period dicts (each has ``period`` + ``accounts``).
        company: B3 ticker for the price overlay; None skips the overlay.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    va_bruta, va_liquida, total_dist = [], [], []
    for p in sorted_periods:
        accounts = p.get("accounts") or {}
        va_bruta.append(_num_or_none((accounts.get("7.04") or {}).get("valor_brl")))
        va_liquida.append(_num_or_none((accounts.get("7.06") or {}).get("valor_brl")))
        total_dist.append(_num_or_none((accounts.get("7.08") or {}).get("valor_brl")))
    if not any(v is not None for v in va_bruta + va_liquida + total_dist):
        return None

    datasets = [
        {"label": "VA Bruta", "data": va_bruta,
         "borderColor": "#0d9488", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "VA Líquida", "data": va_liquida,
         "borderColor": "#f59e0b", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "Total a Distribuir", "data": total_dist,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]
    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }
    has_overlay = _attach_price_overlay(datasets, scales, company, labels)
    description = (
        "Valor Adicionado Bruto (7.04), Líquido (7.06) e Total a "
        "Distribuir (7.08)."
    )
    if has_overlay:
        description += (
            " Linha roxa tracejada = preço de fechamento de fim de período (eixo direito)."
        )
    return {
        "type": "chart",
        "title": "Trajetória da Geração de Valor",
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True,
                              "text": "Geração de Valor Adicionado por Período"},
                },
            },
        },
    }


def build_balanco_chart(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
) -> list[dict]:
    """Build the Balanço Completo charts: absolute + percentage stacked bars.

    [v1.22 v2] REWRITE per user reference images:
    - 2 stacked bar charts (not line charts):
      1. Absolute values: 5 components stacked (Ativo Circ, Ativo Não Circ,
         Passivo Circ, Passivo Não Circ, PL)
      2. 100% percentage composition: same 5 components, normalized to 100%
    - Colors match reference: Navy blue (Ativo Circ), Light blue (Ativo Não
      Circ), Dark red (Passivo Circ), Light pink (Passivo Não Circ), Green (PL)
    - Returns a LIST of 2 chart sections (was 1 dict).

    [v1.24] Quarterly support: when ``bpa_result_q`` + ``bpp_result_q`` are
    provided, the chart uses quarterly periods (up to 20) instead of annual.
    Quarterly data shows finer-grained balance-sheet evolution. Falls back
    to annual when quarterly is unavailable.
    """
    # [v1.24] Prefer quarterly periods when available
    if bpa_result_q and bpp_result_q:
        bpa_periods = (bpa_result_q or {}).get("periods") or []
        bpp_periods = (bpp_result_q or {}).get("periods") or []
    else:
        bpa_periods = (bpa_result or {}).get("periods") or []
        bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return []

    bpa_by_year: dict[str, dict] = {}
    for p in bpa_periods:
        period_label = p.get("period") or p.get("data_fim_exerc") or ""
        if period_label:
            bpa_by_year[str(period_label)] = p.get("accounts") or {}

    bpp_by_year: dict[str, dict] = {}
    for p in bpp_periods:
        period_label = p.get("period") or p.get("data_fim_exerc") or ""
        if period_label:
            bpp_by_year[str(period_label)] = p.get("accounts") or {}

    # [v1.24] Sort period labels chronologically (handles both "2023" annual
    # and "2T2026" quarterly — alphabetical sort would put "1T2026" before
    # "4T2025" which is wrong).
    def _label_sort_key(lbl: str) -> tuple:
        # Quarterly labels look like "2T2026" → (year, quarter)
        if "T" in lbl and len(lbl) >= 6:
            try:
                q = int(lbl.split("T")[0])
                y = int(lbl.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                pass
        # Annual labels look like "2023" → (year, 0)
        try:
            return (int(lbl), 0)
        except ValueError:
            return (0, 0, lbl)

    years = sorted(set(bpa_by_year.keys()) & set(bpp_by_year.keys()),
                   key=_label_sort_key)
    if len(years) < 2:
        years = sorted(set(bpa_by_year.keys()) | set(bpp_by_year.keys()),
                       key=_label_sort_key)
    if len(years) < 2:
        return []

    def _val(accounts: dict, *codes: str) -> float | None:
        for code in codes:
            acc = accounts.get(code)
            if acc and acc.get("valor_brl") is not None:
                try:
                    return float(acc["valor_brl"])
                except (TypeError, ValueError):
                    pass
        return None

    ativo_circ, ativo_ncirc = [], []
    passivo_circ, passivo_ncirc, pl = [], [], []
    for year in years:
        bpa_acc = bpa_by_year.get(year, {})
        bpp_acc = bpp_by_year.get(year, {})
        ativo_circ.append(_num_or_none(_val(bpa_acc, "1.01")))
        ativo_ncirc.append(_num_or_none(_val(bpa_acc, "1.02")))
        passivo_circ.append(_num_or_none(_val(bpp_acc, "2.01")))
        passivo_ncirc.append(_num_or_none(_val(bpp_acc, "2.02")))
        pl_val = _val(bpp_acc, "2.03")
        if pl_val is None:
            pl_val = _val(bpp_acc, "2.08")
        pl.append(_num_or_none(pl_val))

    # Colors matching reference images
    _CIRC_A = "#1e3a5f"      # Navy blue (Ativo Circulante)
    _NCIRC_A = "#60a5fa"     # Light blue (Ativo Não Circulante)
    _CIRC_P = "#991b1b"      # Dark red (Passivo Circulante)
    _NCIRC_P = "#fca5a5"     # Light pink (Passivo Não Circulante)
    _PL = "#22c55e"          # Green (Patrimônio Líquido)

    datasets_abs = [
        {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
        {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
        {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
        {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
        {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": _PL},
    ]

    # Compute percentage datasets (normalize each period to 100%)
    def _pct_series(*series_list):
        """Normalize multiple series to 100% per period."""
        result = []
        for i in range(len(years)):
            total = sum(s[i] or 0 for s in series_list)
            if total == 0:
                result.append([None] * len(series_list))
            else:
                result.append([(s[i] or 0) / total * 100 for s in series_list])
        # Transpose: return list of series, each with per-period values
        return [[result[i][j] for i in range(len(years))] for j in range(len(series_list))]

    pct_data = _pct_series(ativo_circ, ativo_ncirc, passivo_circ, passivo_ncirc, pl)
    datasets_pct = [
        {"label": "Ativo Circulante", "data": pct_data[0], "backgroundColor": _CIRC_A},
        {"label": "Ativo Não Circulante", "data": pct_data[1], "backgroundColor": _NCIRC_A},
        {"label": "Passivo Circulante", "data": pct_data[2], "backgroundColor": _CIRC_P},
        {"label": "Passivo Não Circulante", "data": pct_data[3], "backgroundColor": _NCIRC_P},
        {"label": "Patrimônio Líquido", "data": pct_data[4], "backgroundColor": _PL},
    ]

    return [
        {
            "type": "chart",
            "title": "Balanço Completo — Valores Absolutos",
            "description": "Ativo (Circ + Não Circ) e Passivo + PL (Circ + Não Circ + PL). Barras empilhadas mostram a evolução absoluta.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": years, "datasets": datasets_abs},
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "scales": {
                        "x": {"stacked": True},
                        "y": {"stacked": True, "ticks": {},
                              "title": {"display": True, "text": "R$"}},
                    },
                    "plugins": {
                        "title": {"display": True, "text": "Balanço Patrimonial — Absoluto"},
                        "legend": {"display": True, "position": "top"},
                    },
                },
            },
        },
        {
            "type": "chart",
            "title": "Balanço Completo — Composição Percentual",
            "description": "Mesmos componentes, normalizados para 100% por período. Mostra a mudança na estrutura do balanço.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": years, "datasets": datasets_pct},
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "scales": {
                        "x": {"stacked": True},
                        "y": {"stacked": True, "min": 0, "max": 100,
                              "ticks": {"callback": "{}%"},
                              "title": {"display": True, "text": "%"}},
                    },
                    "plugins": {
                        "title": {"display": True, "text": "Balanço Patrimonial — % Composição"},
                        "legend": {"display": True, "position": "top"},
                        "tooltip": {"callbacks": {"label": "{}%"}},
                    },
                },
            },
        },
    ]


def build_balanco_decomp_charts(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
) -> list[dict]:
    """Build BPA + BPP decomposition charts: 4 stacked bars (absolute + percentage each).

    [v1.22 v2] REWRITE per user reference images:
    - BPA: 2 charts (absolute + percentage) — Ativo Circ + Ativo Não Circ
    - BPP: 2 charts (absolute + percentage) — Passivo Circ + Passivo Não Circ + PL
    - Returns 4 chart sections total.

    [v1.24] Quarterly support: when ``bpa_result_q`` + ``bpp_result_q`` are
    provided, the chart uses quarterly periods (up to 20) instead of annual.
    Falls back to annual when quarterly is unavailable.
    """
    # [v1.24] Prefer quarterly periods when available
    if bpa_result_q and bpp_result_q:
        bpa_periods = (bpa_result_q or {}).get("periods") or []
        bpp_periods = (bpp_result_q or {}).get("periods") or []
    else:
        bpa_periods = (bpa_result or {}).get("periods") or []
        bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return []

    bpa_by_year: dict[str, dict] = {}
    for p in bpa_periods:
        period_label = p.get("period") or p.get("data_fim_exerc") or ""
        if period_label:
            bpa_by_year[str(period_label)] = p.get("accounts") or {}

    bpp_by_year: dict[str, dict] = {}
    for p in bpp_periods:
        period_label = p.get("period") or p.get("data_fim_exerc") or ""
        if period_label:
            bpp_by_year[str(period_label)] = p.get("accounts") or {}

    # [v1.24] Sort period labels chronologically (handles both "2023" annual
    # and "2T2026" quarterly — alphabetical sort would put "1T2026" before
    # "4T2025" which is wrong).
    def _label_sort_key(lbl: str) -> tuple:
        # Quarterly labels look like "2T2026" → (year, quarter)
        if "T" in lbl and len(lbl) >= 6:
            try:
                q = int(lbl.split("T")[0])
                y = int(lbl.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                pass
        # Annual labels look like "2023" → (year, 0)
        try:
            return (int(lbl), 0)
        except ValueError:
            return (0, 0, lbl)

    years = sorted(set(bpa_by_year.keys()) & set(bpp_by_year.keys()),
                   key=_label_sort_key)
    if len(years) < 2:
        years = sorted(set(bpa_by_year.keys()) | set(bpp_by_year.keys()),
                       key=_label_sort_key)
    if len(years) < 2:
        return []

    def _val(accounts: dict, *codes: str) -> float | None:
        for code in codes:
            acc = accounts.get(code)
            if acc and acc.get("valor_brl") is not None:
                try:
                    return float(acc["valor_brl"])
                except (TypeError, ValueError):
                    pass
        return None

    ativo_circ, ativo_ncirc = [], []
    passivo_circ, passivo_ncirc, pl = [], [], []
    for year in years:
        bpa_acc = bpa_by_year.get(year, {})
        bpp_acc = bpp_by_year.get(year, {})
        ativo_circ.append(_num_or_none(_val(bpa_acc, "1.01")))
        ativo_ncirc.append(_num_or_none(_val(bpa_acc, "1.02")))
        passivo_circ.append(_num_or_none(_val(bpp_acc, "2.01")))
        passivo_ncirc.append(_num_or_none(_val(bpp_acc, "2.02")))
        pl_val = _val(bpp_acc, "2.03")
        if pl_val is None:
            pl_val = _val(bpp_acc, "2.08")
        pl.append(_num_or_none(pl_val))

    # Colors matching reference
    _CIRC_A = "#1e3a5f"      # Navy blue
    _NCIRC_A = "#60a5fa"     # Light blue
    _CIRC_P = "#991b1b"      # Dark red
    _NCIRC_P = "#fca5a5"     # Light pink
    _PL = "#22c55e"          # Green

    def _pct(*series_list):
        result = []
        for i in range(len(years)):
            total = sum(s[i] or 0 for s in series_list)
            if total == 0:
                result.append([None] * len(series_list))
            else:
                result.append([(s[i] or 0) / total * 100 for s in series_list])
        return [[result[i][j] for i in range(len(years))] for j in range(len(series_list))]

    bpa_pct = _pct(ativo_circ, ativo_ncirc)
    bpp_pct = _pct(passivo_circ, passivo_ncirc, pl)

    charts: list[dict] = []

    # BPA Absolute
    charts.append({
        "type": "chart",
        "title": "Ativo — Valores Absolutos",
        "description": "Ativo Circulante + Ativo Não Circulante. Barras empilhadas.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
                {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True,
                    "title": {"display": True, "text": "R$"}}},
                "plugins": {"title": {"display": True, "text": "Ativo — Absoluto"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    # BPA Percentage
    charts.append({
        "type": "chart",
        "title": "Ativo — Composição Percentual",
        "description": "Ativo Circulante vs Não Circulante, normalizado para 100%.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Ativo Circulante", "data": bpa_pct[0], "backgroundColor": _CIRC_A},
                {"label": "Ativo Não Circulante", "data": bpa_pct[1], "backgroundColor": _NCIRC_A},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True, "min": 0, "max": 100,
                    "ticks": {"callback": "{}%"}, "title": {"display": True, "text": "%"}}},
                "plugins": {"title": {"display": True, "text": "Ativo — % Composição"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    # BPP Absolute
    charts.append({
        "type": "chart",
        "title": "Passivo + PL — Valores Absolutos",
        "description": "Passivo Circulante + Passivo Não Circulante + Patrimônio Líquido. Barras empilhadas.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
                {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
                {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": _PL},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True,
                    "title": {"display": True, "text": "R$"}}},
                "plugins": {"title": {"display": True, "text": "Passivo + PL — Absoluto"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    # BPP Percentage
    charts.append({
        "type": "chart",
        "title": "Passivo + PL — Composição Percentual",
        "description": "Passivo Circulante vs Não Circulante vs PL, normalizado para 100%.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Passivo Circulante", "data": bpp_pct[0], "backgroundColor": _CIRC_P},
                {"label": "Passivo Não Circulante", "data": bpp_pct[1], "backgroundColor": _NCIRC_P},
                {"label": "Patrimônio Líquido", "data": bpp_pct[2], "backgroundColor": _PL},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True, "min": 0, "max": 100,
                    "ticks": {"callback": "{}%"}, "title": {"display": True, "text": "%"}}},
                "plugins": {"title": {"display": True, "text": "Passivo + PL — % Composição"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    return charts


def build_period_chart(periods: list[dict], label: str) -> dict | None:
    """Build a multi-line chart for the Anual or Trimestral tabs.

    [v1.16] New chart showing Receita/EBITDA/Lucro Líq. across periods.
    Used by both the Anual and Trimestral tabs (raw period data).
    """
    # Filter out periods without data, sort oldest-first.
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) < 2:
        return None

    labels = [str(p.get("period")) for p in sorted_periods]
    revenue, ebitda, net_income = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        revenue.append(_num_or_none(m.get("receita_liquida")))
        ebitda.append(_num_or_none(m.get("ebitda")))
        net_income.append(_num_or_none(m.get("lucro_liquido")))

    if not any(v is not None for v in revenue + ebitda + net_income):
        return None

    chart_type = "line" if label.lower().startswith("anual") else "bar"
    return {
        "type": "chart",
        "title": f"Trajetória — {label}",
        "description": (
            f"Receita Líquida, EBITDA e Lucro Líquido por período ({label}). "
            "Mostra a evolução temporal dos principais indicadores."
        ),
        "chart_data": {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita Líquida", "data": revenue,
                     "backgroundColor": "#0d9488", "borderColor": "#0d9488"},
                    {"label": "EBITDA", "data": ebitda,
                     "backgroundColor": "#f59e0b", "borderColor": "#f59e0b"},
                    {"label": "Lucro Líquido", "data": net_income,
                     "backgroundColor": "#3b82f6", "borderColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "R$"}}},
                "plugins": {
                    "title": {"display": True,
                              "text": f"Receita, EBITDA e Lucro — {label}"},
                },
            },
        },
    }


# ── [v2.0] DuPont + Altman Z sections ────────────────────────────────────────

def build_dupont_section(ratios_payload: dict) -> dict | None:
    """Build a DuPont 3-step ROE decomposition section.

    Shows the 3 components (Net Margin, Asset Turnover, Equity Multiplier)
    as a table + bar chart. ROE = Net Margin × Asset Turnover × Equity Multiplier.

    [v2.0] New section for the financials dashboard. Uses ratios_payload
    from compute_all_ratios (point-in-time, no history_fn call).
    """
    from skills.cvm.calculations._registry import METRICS

    # dupont_at returns the ROE float; we need the decomposition components.
    # Call dupont_history for the latest entry to get all 4 components.
    try:
        from skills.cvm.calculations.metrics.dupont import dupont_history
        from datetime import date
        today = date.today().isoformat()
        hist = dupont_history("__PLACEHOLDER__", today, today)  # company passed separately
    except Exception:
        hist = []

    # Actually, dupont_history needs the company. Let's use ratios_payload.
    # The compute_all_ratios call returns dupont_roe (the headline float).
    # For the decomposition, we compute it inline from the engines.
    dupont_roe = ratios_payload.get("dupont_roe")
    if dupont_roe is None:
        return None

    # Get components from ratios_payload if available, else compute from engines
    net_margin = ratios_payload.get("net_margin")
    asset_turnover = ratios_payload.get("asset_turnover")
    # equity_multiplier = total_assets / pl — not in ratios_payload, compute
    # from the dupont_roe / (net_margin * asset_turnover) if both available
    equity_multiplier = None
    if net_margin and asset_turnover and net_margin != 0 and asset_turnover != 0:
        equity_multiplier = dupont_roe / (net_margin * asset_turnover)

    rows = [
        ["Margem Líquida", _fmt(net_margin, "pct")],
        ["Giro do Ativo", _fmt(asset_turnover, "num")],
        ["Multiplicador de Capital", _fmt(equity_multiplier, "num")],
        ["ROE (DuPont)", _fmt(dupont_roe, "pct")],
    ]

    return {
        "title": "DuPont — Decomposição do ROE",
        "description": "ROE = Margem Líquida × Giro do Ativo × Multiplicador de Capital.",
        "type": "table",
        "columns": ["Componente", "Valor"],
        "rows": rows,
        "note": "Mostra como o ROE é composto: eficiência operacional (margem), eficiência de ativos (giro) e alavancagem (multiplicador).",
    }


def build_altman_z_section(ratios_payload: dict) -> dict | None:
    """Build an Altman Z-Score risk section.

    Shows the Z-score + zone classification + 5 X-components as a table.
    Z > 2.99 = safe, 1.81-2.99 = grey, < 1.81 = distress.

    [v2.0] New section for the financials dashboard. Uses ratios_payload
    from compute_all_ratios (point-in-time, no history_fn call).
    """
    altman_z = ratios_payload.get("altman_z")
    if altman_z is None:
        return None

    # Zone classification
    if altman_z > 2.99:
        zone = "Seguro (Z > 2.99)"
        zone_color = "#22c55e"
    elif altman_z > 1.81:
        zone = "Cinzento (1.81 - 2.99)"
        zone_color = "#f59e0b"
    else:
        zone = "Risco (< 1.81)"
        zone_color = "#ef4444"

    rows = [
        [{"text": "Altman Z-Score",
          "tooltip": "Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5"},
         f"{altman_z:.2f}"],
        [{"text": "Zona",
          "tooltip": "Z > 2.99 seguro, 1.81-2.99 cinzento, < 1.81 risco"},
         zone],
    ]

    return {
        "title": "Altman Z-Score — Risco de Falência",
        "description": "Modelo de 1968 para manufatura. Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5.",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": rows,
        "note": "X2 usa PL como proxy para lucros retidos (engine BPP 2.03.03+2.03.04 não existe ainda). Interpretar com cautela para empresas não-manufatureiras (bancos, serviços).",
    }


def build_wacc_section(ratios_payload: dict) -> dict | None:
    """Build a WACC (Cost of Capital) section.

    Shows WACC + ROE + ROIC so users can see if the company is creating
    value (ROE/ROIC > WACC = creating value).

    [v2.0] New section for the financials dashboard.
    """
    wacc = ratios_payload.get("wacc")
    if wacc is None:
        return None

    roe = ratios_payload.get("roe")
    roic = ratios_payload.get("roic")

    # [v1.25] Tooltips on the FIRST column (metric name), not the value.
    def _label(text: str, tooltip: str) -> dict:
        return {"text": text, "tooltip": tooltip}

    rows = [
        [_label("WACC", "WACC = COE × E/(D+E) + Kd×(1-tax) × D/(D+E)"),
         _fmt(wacc, "pct")],
        [_label("ROE",  "ROE = Lucro Líquido / Patrimônio Líquido"),
         _fmt(roe,  "pct")],
        [_label("ROIC", "ROIC = NOPAT / Capital Investido"),
         _fmt(roic, "pct")],
    ]

    # Value creation assessment
    if roe is not None and wacc is not None:
        spread = roe - wacc
        if spread > 0:
            assessment = f"Criando valor (ROE - WACC = +{spread*100:.1f}%)"
        else:
            assessment = f"Destruindo valor (ROE - WACC = {spread*100:.1f}%)"
        rows.append([
            _label("Avaliação", "Se ROE > WACC, a empresa cria valor"),
            assessment,
        ])

    return {
        "title": "WACC — Custo de Capital vs Retorno",
        "description": "WACC = COE × E/(D+E) + Kd×(1-tax) × D/(D+E). Se ROE/ROIC > WACC, a empresa cria valor.",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": rows,
    }


# ── v1.22: Radar chart + Heatmap (adapted from valuation v2.0) ───────────────

def build_financials_radar(ratios_payload: dict | None) -> dict | None:
    """Build a radar chart comparing key financial dimensions.

    Shows 6 axes: Rentabilidade (ROE), Crescimento (revenue_growth_1y),
    Liquidez (current_ratio), Alavancagem (inverse of D/E), Margem (net_margin),
    Eficiência (asset_turnover). All values normalized to 0-100 scale.

    Returns a chart section dict, or None if fewer than 3 metrics available.
    """
    if not isinstance(ratios_payload, dict):
        return None
    # [v1.22 fix] In financials, ratios_payload is a FLAT dict ({"roe": 0.31, ...}),
    # NOT wrapped in {"ratios": {...}}. Use it directly.
    ratios = ratios_payload

    def _norm_pct(val, max_val=0.5):
        if val is None: return None
        return max(0, min(100, (val / max_val) * 100))

    def _norm_ratio(val, max_val=3.0):
        if val is None: return None
        return max(0, min(100, (val / max_val) * 100))

    def _norm_inverse(val, max_val=3.0):
        if val is None: return None
        return max(0, 100 - min(100, (val / max_val) * 100))

    roe_score = _norm_pct(ratios.get("roe"), 0.4)
    growth_score = _norm_pct(ratios.get("revenue_growth_1y"), 0.3)
    liq_score = _norm_ratio(ratios.get("current_ratio"), 3.0)
    lev_score = _norm_inverse(ratios.get("debt_equity"), 3.0)
    margin_score = _norm_pct(ratios.get("net_margin"), 0.3)
    eff_score = _norm_ratio(ratios.get("asset_turnover"), 2.0)

    scores = [roe_score, growth_score, liq_score, lev_score, margin_score, eff_score]
    if sum(1 for s in scores if s is not None) < 3:
        return None

    chart_data = {
        "type": "radar",
        "data": {
            "labels": ["Rentabilidade", "Crescimento", "Liquidez", "Alavancagem", "Margem", "Eficiência"],
            "datasets": [{
                "label": "Score (0-100)",
                "data": scores,
                "borderColor": "#0d9488",
                "backgroundColor": "rgba(13,148,136,0.15)",
                "pointBackgroundColor": "#0d9488",
                "pointBorderColor": "#fff",
                "pointHoverBackgroundColor": "#fff",
                "pointHoverBorderColor": "#0d9488",
                "borderWidth": 2,
            }],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "r": {
                    "beginAtZero": True,
                    "max": 100,
                    "ticks": {"stepSize": 20},
                    "pointLabels": {"font": {"size": 12}},
                },
            },
            "plugins": {
                "legend": {"display": True, "position": "top"},
                "tooltip": {"mode": "index", "intersect": False},
            },
        },
    }

    return {
        "type": "chart",
        "title": "Radar Financeiro — Visão Multidimensional",
        "description": (
            "Score 0-100 por dimensão. Rentabilidade: ROE. Crescimento: receita 1Y. "
            "Liquidez: corrente. Alavancagem: D/E inverso (menor = melhor). "
            "Margem: líquida. Eficiência: giro do ativo."
        ),
        "chart_data": chart_data,
    }


def build_financials_heatmap(ratios_payload: dict | None) -> dict | None:
    """Build a heatmap table of financial metrics with color coding.

    Each metric is color-coded: green (good), yellow (neutral), red (bad).
    Colors are based on standard financial thresholds.

    Returns a heatmap section dict, or None if no data available.
    """
    if not isinstance(ratios_payload, dict):
        return None
    # [v1.22 fix] In financials, ratios_payload is a FLAT dict — use directly.
    ratios = ratios_payload

    def _heat(val, good, bad, reverse=False):
        if val is None:
            return {"text": "—", "bg": "", "color": ""}
        if reverse:
            if val <= good:
                return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
            elif val <= bad:
                return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
            else:
                return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}
        else:
            if val >= good:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
            elif val >= bad:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
            else:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}

    def _heat_ratio(val, good_min, bad_min):
        if val is None:
            return {"text": "—", "bg": "", "color": ""}
        if val >= good_min:
            return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
        elif val >= bad_min:
            return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
        else:
            return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}

    rows = [
        ["ROE", _heat(ratios.get("roe"), 0.20, 0.10)],
        ["ROA", _heat(ratios.get("roa"), 0.10, 0.05)],
        ["ROIC", _heat(ratios.get("roic"), 0.12, 0.07)],
        ["Margem Líquida", _heat(ratios.get("net_margin"), 0.15, 0.05)],
        ["Margem EBITDA", _heat(ratios.get("ebitda_margin"), 0.25, 0.10)],
        ["Margem Operacional", _heat(ratios.get("operating_margin"), 0.15, 0.05)],
        ["D/E", _heat(ratios.get("debt_equity"), 0.5, 2.0, reverse=True)],
        ["Dív. Líq./EBITDA", _heat(ratios.get("net_debt_ebitda"), 1.5, 3.5, reverse=True)],
        ["Liquidez Corrente", _heat_ratio(ratios.get("current_ratio"), 1.5, 1.0)],
        ["Cresc. Receita 1Y", _heat(ratios.get("revenue_growth_1y"), 0.10, 0.0)],
    ]

    return {
        "type": "heatmap",
        "title": "Heatmap Financeiro — Indicadores Coloridos",
        "description": (
            "Verde = bom, Amarelo = neutro, Vermelho = ruim. "
            "Thresholds baseados em práticas para B3."
        ),
        "columns": ["Métrica", "Valor"],
        "rows": rows,
    }
