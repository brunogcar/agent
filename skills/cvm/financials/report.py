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
        rows = [
            ["Período",           latest_annual_period.get("period", "—")],
            ["Receita Líquida",   _fmt(m.get("receita_liquida"),   "brl")],
            ["Lucro Bruto",       _fmt(m.get("lucro_bruto"),       "brl")],
            ["EBIT",              _fmt(m.get("ebit"),              "brl")],
            ["EBITDA",            _fmt(m.get("ebitda"),            "brl")],
            ["Lucro Líquido",     _fmt(m.get("lucro_liquido"),     "brl")],
            ["Margem Bruta",      _fmt(r.get("marg_bruta"),        "pct")],
            ["Margem EBITDA",     _fmt(r.get("marg_ebitda"),       "pct")],
            ["Margem Líquida",    _fmt(r.get("marg_liquida"),      "pct")],
            ["Ativo Total",       _fmt(m.get("ativo_total"),       "brl")],
            ["Patrimônio Liq.",   _fmt(m.get("patrimonio_liquido"),"brl")],
            ["Caixa",             _fmt(m.get("caixa"),             "brl")],
            ["Divida Bruta",      _fmt(m.get("divida_bruta"),      "brl")],
            ["FCO",               _fmt(m.get("fco"),               "brl")],
            ["FCI",               _fmt(m.get("fci"),               "brl")],
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
    "roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin",
    "ebitda_margin", "ocf_margin", "fcf_margin",
    "debt_equity", "cash_flow_to_debt", "capex_revenue",
    "retention_ratio", "sustainable_growth",
    "dpa", "effective_tax_rate",
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
_INDICADORES_CATEGORIES = [
    "valuation", "profitability", "liquidity",
    "leverage", "efficiency", "growth", "tax",
]

def _group_metrics_by_prefix(items: list[dict], category_label: str = "") -> list[dict]:
    """Group metric items by their label prefix (EV/, P/, ROE, etc.).

    Items with labels starting with "EV/" go into "EV" group.
    Items with labels starting with "P/" go into "P/" group.
    Growth items split by underlying metric (Receita/Lucro Líq./Resultado Bruto).
    Everything else goes into a group named after the category (e.g. "Liquidez",
    "Endividamento") instead of the generic "Outros".

    [new commit] The "Outros" bucket is now named after the category_label
    parameter (e.g. "Liquidez", "Endividamento", "Tributos"). User feedback:
    "box Outros - should be liquidez". For growth, keeps "Outros Crescimento".
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        label = item.get("label", "")
        if label.startswith("EV/"):
            gname = "EV (Enterprise Value)"
        elif label.startswith("P/"):
            gname = "P/ (Price)"
        elif label.startswith("Marg."):
            gname = "Margens"
        elif label.startswith("Giro"):
            gname = "Giro"
        elif label in ("ROE", "ROA", "ROIC"):
            gname = "Retorno"
        elif label.startswith("Crescimento Receita"):
            gname = "Receita"
        elif label.startswith("Crescimento Lucro"):
            gname = "Lucro Líquido"
        elif label.startswith("Crescimento Resultado"):
            gname = "Resultado Bruto"
        elif label.startswith("Crescimento"):
            gname = "Outros Crescimento"
        else:
            # [new commit] Use the category label instead of generic "Outros"
            gname = category_label if category_label else "Outros"
        groups.setdefault(gname, []).append(item)

    # Return in a sensible order
    order = [
        "EV (Enterprise Value)", "P/ (Price)", "Retorno", "Margens",
        "Giro",
        "Receita", "Lucro Líquido", "Resultado Bruto",
        "Outros Crescimento", "Outros",
    ]
    result = []
    for gname in order:
        if gname in groups:
            result.append({"label": gname, "items": groups[gname]})
    # Add any groups not in the order list
    for gname, gitems in groups.items():
        if gname not in order:
            result.append({"label": gname, "items": gitems})
    return result


def build_indicadores_section(today: str, ratios_payload: dict) -> dict:
    """Build the Indicadores tab as a ``type: "subtabs"`` section.

    [v1.16] First sub-tab "Todas" shows ALL categories in one ratio_grid.
    Then individual category sub-tabs follow, each with items sub-grouped
    by prefix (EV/, P/, Retorno, Margens, etc.) within the ratio_grid.

    [v1.18] Each category subtab now also includes a bar chart showing
    the numeric values of that category's metrics — visual comparison
    alongside the ratio_grid.
    """
    sub_tabs: list[dict] = []
    try:
        from skills.cvm.calculations._registry import (
            METRICS, list_metrics_by_category,
        )

        # First sub-tab: "Todas" — all categories in one ratio_grid
        all_cats: list[dict] = []
        for category in _INDICADORES_CATEGORIES:
            metrics_in_cat = list_metrics_by_category(category)
            if not metrics_in_cat:
                continue
            items: list[dict] = []
            for metric_name in metrics_in_cat:
                # [new commit] Exclude raw-number metrics from "Todas" too
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
                    "tooltip": tooltip,
                })
            if items:
                cat_label = _RATIO_CATEGORY_LABELS.get(category, category.capitalize())
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

        # Individual category sub-tabs with prefix sub-grouping
        for category in _INDICADORES_CATEGORIES:
            metrics_in_cat = list_metrics_by_category(category)
            if not metrics_in_cat:
                continue
            items: list[dict] = []
            for metric_name in metrics_in_cat:
                # [new commit] Exclude raw-number metrics (working_capital)
                # from Indicadores — they're not ratios.
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
                    # Avoids fragile parsing of formatted strings (was a P0
                    # bug — PT-BR "1.234,56" broke float() parse).
                    "value_raw": float(value) if value is not None else None,
                    "tooltip": tooltip,
                })
            if items:
                cat_label = _RATIO_CATEGORY_LABELS.get(category, category.capitalize())
                # [v1.16] Sub-group by prefix within each category
                # [new commit] Pass cat_label so "Outros" bucket is named
                # after the category (e.g. "Liquidez", "Endividamento").
                grouped = _group_metrics_by_prefix(items, category_label=cat_label)
                sub_sections: list[dict] = [{
                    "title": f"{cat_label} (as of {today})",
                    "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
                    "type": "ratio_grid",
                    "categories": grouped,
                }]
                # [v1.16.1] Add a bar chart showing numeric values for this
                # category's metrics. Uses value_raw (not the formatted string)
                # to avoid the PT-BR decimal-comma parse bug.
                chart_labels = []
                chart_values = []
                for item in items:
                    raw = item.get("value_raw")
                    if raw is not None:
                        # [new commit] F15 fix: scale 0-1 fractions to 0-100
                        # for chart display (ROE 0.26 → 26). Was showing raw
                        # 0.26 on the y-axis instead of 26. Matches the
                        # pattern used in build_crescimento_sections + valuation.
                        if abs(raw) < 1:
                            raw = raw * 100
                        chart_labels.append(item["label"])
                        chart_values.append(raw)
                if len(chart_labels) >= 2:
                    sub_sections.append({
                        "type": "chart",
                        "title": f"{cat_label} — Comparativo Visual",
                        "description": f"Valores numéricos dos indicadores de {cat_label}.",
                        "chart_data": {
                            "type": "bar",
                            "data": {
                                "labels": chart_labels,
                                "datasets": [{
                                    "label": cat_label,
                                    "data": chart_values,
                                    "backgroundColor": "#0d9488",
                                }],
                            },
                            "options": {
                                "responsive": True,
                                "maintainAspectRatio": False,
                                "scales": {"y": {"ticks": {}}},
                                "plugins": {
                                    "title": {"display": True, "text": f"{cat_label} — Valores"},
                                },
                            },
                        },
                    })
                sub_tabs.append({
                    "name": cat_label,
                    "sections": sub_sections,
                })
    except Exception:
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


def build_crescimento_sections(
    latest_annual_period: dict | None,
    annual_periods: list[dict],
    quarterly_periods: list[dict] | None = None,
    ratios_payload: dict | None = None,
) -> list[dict]:
    """Build the Crescimento tab: 3M/1Y/5Y growth table + bar chart.

    [new commit] MAJOR REWRITE — delegates to ratios_payload (computed via
    the calculations registry + FIXED growth_at anchoring). This eliminates:
      - F8: lexicographic quarter sort bug (no longer sorts quarters)
      - F10: duplicate growth logic (now uses same path as Indicadores)
      - F19: zero-guard too strict (delegated to growth_helpers)
    The old implementation called growth_at() on ANNUAL periods + had its
    own _qoq_growth with the lexicographic sort bug. Now both 3M/1Y/5Y
    come from ratios_payload which uses TTM periods + the anchored prior
    search (consistent with the historical dashboard).
    """
    sections: list[dict] = []

    rp = ratios_payload or {}
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

    # If ALL values are None, show unavailable message.
    all_vals = [rev_3m, rev_1y, rev_5y, gp_3m, gp_1y, gp_5y, ni_3m, ni_1y, ni_5y]
    if all(v is None for v in all_vals):
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

    # Bar chart: 3M + 1Y + 5Y for each metric.
    chart_data_1y = [rev_1y, gp_1y, ni_1y]
    chart_data_5y = [rev_5y, gp_5y, ni_5y]
    chart_data_3m = [rev_3m, gp_3m, ni_3m]
    if any(v is not None for v in chart_data_1y + chart_data_5y + chart_data_3m):
        datasets = []
        if any(v is not None for v in chart_data_3m):
            datasets.append({
                "label": "3M (QoQ TTM)",
                "data": [(_v * 100 if _v is not None else None) for _v in chart_data_3m],
                "backgroundColor": "#a855f7",
            })
        if any(v is not None for v in chart_data_1y):
            datasets.append({
                "label": "1Y",
                "data": [(_v * 100 if _v is not None else None) for _v in chart_data_1y],
                "backgroundColor": "#22c55e",
            })
        if any(v is not None for v in chart_data_5y):
            datasets.append({
                "label": "5Y",
                "data": [(_v * 100 if _v is not None else None) for _v in chart_data_5y],
                "backgroundColor": "#3b82f6",
            })
        sections.append({
            "type": "chart",
            "title": "Crescimento Comparativo (3M / 1Y / 5Y)",
            "description": (
                "Crescimento percentual de Receita Líquida, Lucro Bruto e "
                "Lucro Líquido nos três horizontes temporais. Barras "
                "ausentes indicam dados insuficientes para o cálculo."
            ),
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": ["Receita Líquida", "Lucro Bruto", "Lucro Líquido"],
                    "datasets": datasets,
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
                        "title": {"display": True, "text": "Crescimento por Horizonte Temporal"},
                    },
                },
            },
        })

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


def build_balanco_section(bpa_result: dict, bpp_result: dict) -> dict:
    """Build the Balanço tab as a `type: "subtabs"` section with BPA + BPP.

    [new commit] Added "Completo" sub-tab (first) showing BPA + BPP combined
    in one table. User feedback: "add first tab being full bpa+bpp".
    """
    sub_tabs: list[dict] = []

    bpa_periods = (bpa_result or {}).get("periods") or []
    bpp_periods = (bpp_result or {}).get("periods") or []

    # [new commit] First sub-tab: "Completo" — BPA + BPP combined
    if bpa_periods and bpp_periods:
        latest_bpa = bpa_periods[0]
        latest_bpp = bpp_periods[0]
        bpa_accounts = latest_bpa.get("accounts") or {}
        bpp_accounts = latest_bpp.get("accounts") or {}
        if bpa_accounts and bpp_accounts:
            # Merge into a single table with Ativo section first, then Passivo
            merged_section = _statement_table_section(
                f"Balanço Completo — {latest_bpa.get('period') or 'Latest'}",
                {**bpa_accounts, **bpp_accounts},
            )
            sub_tabs.append({
                "name": "Completo",
                "sections": [merged_section],
            })

    # BPA sub-tab
    if bpa_periods:
        latest_bpa = bpa_periods[0]
        accounts = latest_bpa.get("accounts") or {}
        if accounts:
            sub_tabs.append({
                "name": "BPA",
                "sections": [_statement_table_section(
                    f"Ativo — {latest_bpa.get('period') or latest_bpa.get('data_fim_exerc') or 'Latest'}",
                    accounts,
                )],
            })
    if not any(st["name"] == "BPA" for st in sub_tabs):
        sub_tabs.append({
            "name": "BPA",
            "sections": [{
                "type": "text",
                "text": "BPA data unavailable for this company.",
            }],
        })

    # BPP sub-tab
    if bpp_periods:
        latest_bpp = bpp_periods[0]
        accounts = latest_bpp.get("accounts") or {}
        if accounts:
            sub_tabs.append({
                "name": "BPP",
                "sections": [_statement_table_section(
                    f"Passivo — {latest_bpp.get('period') or latest_bpp.get('data_fim_exerc') or 'Latest'}",
                    accounts,
                )],
            })
    if not any(st["name"] == "BPP" for st in sub_tabs):
        sub_tabs.append({
            "name": "BPP",
            "sections": [{
                "type": "text",
                "text": "BPP data unavailable for this company.",
            }],
        })

    return {
        "type": "subtabs",
        "tabs": sub_tabs,
    }


# ── Tab 5: DRE (table + margin trend chart) ──────────────────────────────────

def build_dre_sections(
    dre_result: dict,
    annual_periods: list[dict],
    latest_annual_period: dict | None,
) -> list[dict]:
    """Build the DRE tab: latest annual accounts table + 5Y margin trend chart."""
    sections: list[dict] = []

    # DRE table from the standalone dre() mode (latest period).
    dre_periods = (dre_result or {}).get("periods") or []
    if dre_periods:
        latest = dre_periods[0]
        accounts = latest.get("accounts") or {}
        if accounts:
            sections.append(_statement_table_section(
                f"DRE — {latest.get('period') or latest.get('data_fim_exerc') or 'Latest'}",
                accounts,
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

    # Margin trend chart: gross/operating/net/EBITDA margins over last 5 years.
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) >= 2:
        labels = [str(p.get("period")) for p in sorted_periods]
        gross = []
        operating = []
        net = []
        ebitda = []
        for p in sorted_periods:
            r = p.get("ratios") or {}
            gross.append(_pct_of(r.get("marg_bruta")))
            operating.append(_pct_of(r.get("marg_ebit")))
            net.append(_pct_of(r.get("marg_liquida")))
            ebitda.append(_pct_of(r.get("marg_ebitda")))
        sections.append({
            "type": "chart",
            "title": "Evolução das Margens (5 anos)",
            "description": (
                "Margens Bruta, EBIT, EBITDA e Líquida ao longo dos últimos "
                "5 anos. Mostra a trajetória da rentabilidade operacional."
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
                        "title": {"display": True, "text": "Margens Operacionais ao Longo do Tempo"},
                    },
                },
            },
        })

    return sections


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
) -> list[dict]:
    """Build the DFC tab: latest annual accounts table + 5Y FCO/FCI/FCF chart."""
    sections: list[dict] = []

    dfc_periods = (dfc_result or {}).get("periods") or []
    if dfc_periods:
        latest = dfc_periods[0]
        accounts = latest.get("accounts") or {}
        if accounts:
            sections.append(_statement_table_section(
                f"DFC — {latest.get('period') or latest.get('data_fim_exerc') or 'Latest'}",
                accounts,
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

    # Stacked bar chart: FCO/FCI/FCF over last 5 annual periods.
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) >= 2:
        labels = [str(p.get("period")) for p in sorted_periods]
        fco = []
        fci = []
        fcf = []
        for p in sorted_periods:
            m = p.get("metrics") or {}
            fco.append(_num_or_none(m.get("fco")))
            fci.append(_num_or_none(m.get("fci")))
            fcf.append(_num_or_none(m.get("fcf")))
        sections.append({
            "type": "chart",
            "title": "Fluxos de Caixa (5 anos, empilhado)",
            "description": (
                "Fluxo de Caixa Operacional (FCO), de Investimento (FCI) "
                "e de Financiamento (FCF) ao longo dos últimos 5 anos. "
                "Barras empilhadas mostram a composição total do fluxo de caixa."
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
        })

    return sections


def _num_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Tab 7: DVA (table + doughnut chart) ──────────────────────────────────────

def build_dva_sections(dva_result: dict) -> list[dict]:
    """Build the DVA tab: generation + distribution table + doughnut chart."""
    sections: list[dict] = []

    dva_periods = (dva_result or {}).get("periods") or []
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

    # Build the table grouped by section (Geração / Distribuição).
    sections.append(_statement_table_section(
        f"DVA — {latest.get('period') or latest.get('data_fim_exerc') or 'Latest'}",
        accounts,
    ))

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

    return sections


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

def build_overview_trend_chart(annual_periods: list[dict]) -> dict | None:
    """Build a multi-line chart showing Receita/EBITDA/Lucro Líq. over annual periods.

    [v1.16] New chart for the Overview tab — gives users an immediate
    visual sense of the company's revenue + earnings trajectory without
    having to navigate to the DRE or Anual tabs.
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

    return {
        "type": "chart",
        "title": "Trajetória de Receita e Lucro (Anual)",
        "description": (
            "Receita Líquida, EBITDA e Lucro Líquido anuais. Mostra a "
            "trajetória de crescimento e rentabilidade da empresa."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita Líquida", "data": revenue,
                     "borderColor": "#0d9488", "fill": False, "tension": 0.3},
                    {"label": "EBITDA", "data": ebitda,
                     "borderColor": "#f59e0b", "fill": False, "tension": 0.3},
                    {"label": "Lucro Líquido", "data": net_income,
                     "borderColor": "#3b82f6", "fill": False, "tension": 0.3},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "R$"}}},
                "plugins": {
                    "title": {"display": True, "text": "Receita, EBITDA e Lucro Líquido"},
                },
            },
        },
    }


def build_balanco_chart(bpa_result: dict, bpp_result: dict) -> dict | None:
    """Build the accounting equation chart: Ativo = Passivo + PL over years.

    [new commit] MAJOR REWRITE per user feedback:
    - Chart now shows Ativo Total vs (Passivo Total + PL) as two lines
      to visualize the accounting equation Ativo = Passivo + PL.
    - Note added explaining this is not the default display.
    - Removed dead `caixa` variable (F18).
    - Added two new charts: Ativo decomposition (Circ + Não Circ) and
      Passivo decomposition (Circ + Não Circ + PL).
    """
    bpa_periods = (bpa_result or {}).get("periods") or []
    bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return None

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

    years = sorted(set(bpa_by_year.keys()) & set(bpp_by_year.keys()))
    if len(years) < 2:
        years = sorted(set(bpa_by_year.keys()) | set(bpp_by_year.keys()))
    if len(years) < 2:
        return None

    def _val(accounts: dict, *codes: str) -> float | None:
        for code in codes:
            acc = accounts.get(code)
            if acc and acc.get("valor_brl") is not None:
                try:
                    return float(acc["valor_brl"])
                except (TypeError, ValueError):
                    pass
        return None

    ativo_total, passivo_total, pl = [], [], []
    ativo_circ, ativo_ncirc = [], []
    passivo_circ, passivo_ncirc = [], []
    for year in years:
        bpa_acc = bpa_by_year.get(year, {})
        bpp_acc = bpp_by_year.get(year, {})
        ativo_total.append(_num_or_none(_val(bpa_acc, "1")))
        ativo_circ.append(_num_or_none(_val(bpa_acc, "1.01")))
        ativo_ncirc.append(_num_or_none(_val(bpa_acc, "1.02")))
        pl.append(_num_or_none(_val(bpp_acc, "2.03")))
        passivo_total.append(_num_or_none(_val(bpp_acc, "2")))
        passivo_circ.append(_num_or_none(_val(bpp_acc, "2.01")))
        passivo_ncirc.append(_num_or_none(_val(bpp_acc, "2.02")))

    # Chart 1: Accounting equation — Ativo vs (Passivo + PL)
    # [new commit] Two overlapping lines to visualize Ativo = Passivo + PL.
    passivo_mais_pl = []
    for i in range(len(years)):
        p = passivo_total[i] if i < len(passivo_total) else None
        e = pl[i] if i < len(pl) else None
        if p is not None and e is not None:
            passivo_mais_pl.append(p + e)
        else:
            passivo_mais_pl.append(None)

    return {
        "type": "chart",
        "title": "Equação Contábil: Ativo = Passivo + PL (Anual)",
        "description": (
            "Visualização da equação contábil fundamental: Ativo Total vs "
            "(Passivo Total + Patrimônio Líquido). As linhas devem se "
            "sobrepor quando a equação é válida."
        ),
        "note": (
            "Nota: esta não é a exibição padrão (3 barras separadas). "
            "Aqui sobrepondo Ativo com (Passivo+PL) para validar a "
            "equação contábil. Para ver a decomposição, veja os gráficos "
            "abaixo."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": years,
                "datasets": [
                    {"label": "Ativo Total", "data": ativo_total, "backgroundColor": "#0d9488",
                     "borderColor": "#0d9488", "type": "line", "fill": False, "tension": 0.1},
                    {"label": "Passivo + PL", "data": passivo_mais_pl, "backgroundColor": "#f59e0b",
                     "borderColor": "#f59e0b", "type": "line", "fill": False, "tension": 0.1},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "R$"}}},
                "plugins": {
                    "title": {"display": True, "text": "Ativo vs Passivo + PL"},
                },
            },
        },
    }


def build_balanco_decomp_charts(bpa_result: dict, bpp_result: dict) -> list[dict]:
    """Build decomposition charts: Ativo = Circ + Não Circ, Passivo = Circ + Não Circ + PL.

    [new commit] New function per user feedback:
    "add chart to Ativo Total = Ativo Circulante + Ativo Não Circulante
    and same to passivo total = passivo c + passivo n c, then pl"
    """
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

    years = sorted(set(bpa_by_year.keys()) & set(bpp_by_year.keys()))
    if len(years) < 2:
        years = sorted(set(bpa_by_year.keys()) | set(bpp_by_year.keys()))
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
        pl.append(_num_or_none(_val(bpp_acc, "2.03")))

    charts: list[dict] = []

    # Chart: Ativo Total = Ativo Circulante + Ativo Não Circulante
    charts.append({
        "type": "chart",
        "title": "Ativo Total = Circulante + Não Circulante",
        "description": "Decomposição do Ativo Total em circulante e não circulante.",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": years,
                "datasets": [
                    {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": "#0d9488"},
                    {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": "#14b8a6"},
                ],
            },
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True, "ticks": {},
                    "title": {"display": True, "text": "R$"}}},
                "plugins": {"title": {"display": True, "text": "Composição do Ativo"}},
            },
        },
    })

    # Chart: Passivo Total = Circ + Não Circ + PL
    charts.append({
        "type": "chart",
        "title": "Passivo + PL = Circulante + Não Circulante + PL",
        "description": "Decomposição do Passivo + Patrimônio Líquido.",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": years,
                "datasets": [
                    {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": "#ef4444"},
                    {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": "#f97316"},
                    {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True, "ticks": {},
                    "title": {"display": True, "text": "R$"}}},
                "plugins": {"title": {"display": True, "text": "Composição do Passivo + PL"}},
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
