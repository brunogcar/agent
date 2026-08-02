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
) -> list[dict]:
    """Build 6 KPI cards with pre-formatted values.

    Per the v1.12 dashboard spec: Receita (TTM), EBITDA, Lucro Líquido,
    ROE, ROIC, Dívida Líquida/EBITDA. Values are pre-formatted strings;
    `unit` is kept for the adapter to know which spec was used (so the
    adapter can re-format raw numbers if needed).
    """
    return [
        {
            "label": "Receita (TTM)",
            "value": _fmt(annual_metric(latest_annual_period, "receita_liquida"), "brl"),
            "unit": "BRL",
        },
        {
            "label": "EBITDA",
            "value": _fmt(annual_metric(latest_annual_period, "ebitda"), "brl"),
            "unit": "BRL",
        },
        {
            "label": "Lucro Líquido",
            "value": _fmt(annual_metric(latest_annual_period, "lucro_liquido"), "brl"),
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

def _group_metrics_by_prefix(items: list[dict]) -> list[dict]:
    """Group metric items by their label prefix (EV/, P/, ROE, etc.).

    Items with labels starting with "EV/" go into "EV" group.
    Items with labels starting with "P/" go into "P/" group.
    Growth items split by underlying metric (Receita/Lucro Líq./Resultado Bruto).
    Everything else goes into a "Outros" group.
    Returns a list of {"label": group_name, "items": [...]} dicts.

    [v1.16] Added growth-specific prefixes so the Crescimento subtab
    splits into Receita / Lucro Líquido / Resultado Bruto / Outros
    instead of dumping all 11 growth metrics into a single "Outros".
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
            gname = "Outros"
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
                grouped = _group_metrics_by_prefix(items)
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
) -> list[dict]:
    """Build the Crescimento tab: 3M/1Y/5Y growth table + bar chart.

    [v1.7 review-fix] Growth now uses ``growth_helpers.growth_at()`` with
    period-specific gap tolerance (1.5x for 3M/1Y, 1.2x for 5Y).  This
    handles missing annual periods gracefully: if a company skipped a
    filing year, the helper finds the closest period within the tolerance
    window instead of blindly indexing ``sorted_periods[N]``.

    [v1.16] Now accepts ``quarterly_periods`` to compute 3M growth from
    the latest two standalone quarters. Previously 3M was always "—"
    because only annual data was available. Also added chart title +
    description, and the table now shows a note when 3M is derived
    from quarterly data.

    Growth metrics (Revenue / Gross Profit / Net Income) are derived from
    the annual periods list when available; otherwise the table shows "—"
    and the chart is skipped.
    """
    from skills.cvm.calculations.growth_helpers import (
        growth_at, LOOKBACK_1Y, LOOKBACK_5Y,
    )

    sections: list[dict] = []

    # Determine the "current" date: latest annual period's data_fim_exerc.
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
        reverse=True,
    )
    latest = sorted_periods[0] if sorted_periods else latest_annual_period
    if not latest:
        sections.append({
            "type": "text",
            "text": "Crescimento indisponível — sem períodos anuais.",
        })
        return sections
    target_date = _period_date(latest)

    # Build per-metric period lists for growth_helpers.
    rev_periods = _build_metric_periods(annual_periods, "receita_liquida")
    gp_periods = _build_metric_periods(annual_periods, "lucro_bruto")
    ni_periods = _build_metric_periods(annual_periods, "lucro_liquido")

    rev_1y = growth_at(rev_periods, target_date, LOOKBACK_1Y)
    rev_5y = growth_at(rev_periods, target_date, LOOKBACK_5Y)
    gp_1y = growth_at(gp_periods, target_date, LOOKBACK_1Y)
    gp_5y = growth_at(gp_periods, target_date, LOOKBACK_5Y)
    ni_1y = growth_at(ni_periods, target_date, LOOKBACK_1Y)
    ni_5y = growth_at(ni_periods, target_date, LOOKBACK_5Y)

    # [v1.16] 3M growth from quarterly data: compare the latest standalone
    # quarter vs the immediately preceding quarter. If quarterly_periods
    # is missing or has < 2 entries, 3M stays "—".
    def _qoq_growth(metric_key: str) -> float | None:
        if not quarterly_periods or len(quarterly_periods) < 2:
            return None
        # quarterly_periods are newest-first (from _build_quarterly_summary).
        # Take the first two entries.
        sorted_q = sorted(
            [p for p in quarterly_periods if p.get("period")],
            key=lambda p: str(p.get("period")),
            reverse=True,
        )
        if len(sorted_q) < 2:
            return None
        curr = (sorted_q[0].get("metrics") or {}).get(metric_key)
        prev = (sorted_q[1].get("metrics") or {}).get(metric_key)
        if curr is None or prev is None or prev == 0:
            return None
        return (curr - prev) / abs(prev)

    rev_3m = _qoq_growth("receita_liquida")
    gp_3m = _qoq_growth("lucro_bruto")
    ni_3m = _qoq_growth("lucro_liquido")

    rows = [
        ["Receita Líquida",   _fmt(rev_3m, "pct"), _fmt(rev_1y, "pct"), _fmt(rev_5y, "pct")],
        ["Lucro Bruto",       _fmt(gp_3m, "pct"), _fmt(gp_1y, "pct"), _fmt(gp_5y, "pct")],
        ["Lucro Líquido",     _fmt(ni_3m, "pct"), _fmt(ni_1y, "pct"), _fmt(ni_5y, "pct")],
    ]
    sections.append({
        "title": "Crescimento (3M / 1Y / 5Y)",
        "description": (
            "Crescimento de Receita, Lucro Bruto e Lucro Líquido. 3M = "
            "trimestre vs trimestre anterior (QoQ); 1Y e 5Y usam período "
            "anual com tolerância de gap (1.5x / 1.2x)."
        ),
        "type": "table",
        "columns": ["Métrica", "3M", "1Y", "5Y"],
        "rows": rows,
        "note": (
            "3M = crescimento trimestral (QoQ) derivado de ITR. "
            "1Y/5Y usam períodos anuais com tolerância de gap — um ano "
            "de relatório ausente é compensado se houver período dentro "
            "da janela de tolerância."
        ),
    })

    # Bar chart: 1Y + 5Y for each metric (3M excluded — usually missing).
    chart_data_1y = [rev_1y, gp_1y, ni_1y]
    chart_data_5y = [rev_5y, gp_5y, ni_5y]
    chart_data_3m = [rev_3m, gp_3m, ni_3m]
    if any(v is not None for v in chart_data_1y + chart_data_5y + chart_data_3m):
        datasets = []
        if any(v is not None for v in chart_data_3m):
            datasets.append({
                "label": "3M (QoQ)",
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

    Each sub-tab has a single `type: "table"` section showing the latest
    period's accounts grouped by section.
    """
    sub_tabs: list[dict] = []

    # BPA sub-tab
    bpa_periods = (bpa_result or {}).get("periods") or []
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
    if not sub_tabs or not bpa_periods:
        sub_tabs.append({
            "name": "BPA",
            "sections": [{
                "type": "text",
                "text": "BPA data unavailable for this company.",
            }],
        })

    # BPP sub-tab
    bpp_periods = (bpp_result or {}).get("periods") or []
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
    if len(sub_tabs) < 2 or not bpp_periods:
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

        years = []
        growths = []
        for p in periods:
            year = p.get("year")
            yoy = p.get("yoy_growth") or {}
            growth = yoy.get("receita_liquida")
            if year is not None:
                years.append(str(year))
                all_years.add(year)
                growths.append(_num_or_none(growth) * 100 if growth is not None else None)

        if years:
            datasets.append({
                "label": q_label,
                "data": growths,
            })

    if not datasets:
        return None

    labels = sorted(str(y) for y in all_years)

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
    """Build per-year tables showing same-quarter YoY comparison.

    [v1.18] Restructured to return ONE TABLE PER YEAR (was a single table
    sorted by year). Each year gets its own section with a title like
    "2026" and a table showing all 4 quarters for that year.

    Returns a list of section dicts (one per year), newest year first.
    """
    columns = ["Trimestre", "Receita", "EBITDA", "Lucro Líq.", "Receita YoY %"]

    # Flatten all periods across groups, collect by year.
    by_year: dict[int, list[dict]] = {}
    for g in groups:
        q_label = g.get("quarter", "")
        for p in g.get("periods") or []:
            year = p.get("year")
            if year is None:
                continue
            by_year.setdefault(year, []).append({
                "quarter": q_label,
                "qnum": p.get("quarter", 0),
                "receita": (p.get("metrics") or {}).get("receita_liquida"),
                "ebitda": (p.get("metrics") or {}).get("ebitda"),
                "lucro": (p.get("metrics") or {}).get("lucro_liquido"),
                "yoy": (p.get("yoy_growth") or {}).get("receita_liquida"),
            })

    sections: list[dict] = []
    for year in sorted(by_year.keys(), reverse=True):
        periods = sorted(by_year[year], key=lambda x: x["qnum"])
        rows = []
        for p in periods:
            rows.append([
                p["quarter"],
                _fmt(p["receita"], "brl"),
                _fmt(p["ebitda"], "brl"),
                _fmt(p["lucro"], "brl"),
                _fmt(p["yoy"], "pct"),
            ])
        sections.append({
            "title": str(year),
            "description": f"Trimestres de {year}. YoY % = (atual - anterior) / |anterior|.",
            "type": "table",
            "columns": columns,
            "rows": rows,
        })

    if not sections:
        return [{
            "title": "Comparação YoY por Ano",
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
    """Build a stacked bar chart showing Ativo vs Passivo+PL over annual periods.

    [v1.16] New chart for the Balanço tab — visualizes the balance sheet
    structure over time. Each year has two bars: Ativo (Caixa + Outros)
    and Passivo+PL (Dívida + PL).
    """
    bpa_periods = (bpa_result or {}).get("periods") or []
    bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return None

    # Build a year → accounts dict for BPA and BPP.
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

    # Use the intersection of years, sorted oldest-first.
    years = sorted(set(bpa_by_year.keys()) & set(bpp_by_year.keys()))
    if len(years) < 2:
        # Fall back to union if intersection is too small.
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

    caixa, ativo_total, passivo_total, pl = [], [], [], []
    for year in years:
        bpa_acc = bpa_by_year.get(year, {})
        bpp_acc = bpp_by_year.get(year, {})
        ativo_total.append(_num_or_none(_val(bpa_acc, "1")))
        pl.append(_num_or_none(_val(bpp_acc, "2.03")))
        passivo_total.append(_num_or_none(_val(bpp_acc, "2")))

    return {
        "type": "chart",
        "title": "Estrutura do Balanço (Anual)",
        "description": (
            "Ativo Total, Passivo Total e Patrimônio Líquido ao longo dos "
            "anos. Mostra a estrutura de capital e a equação contábil "
            "Ativo = Passivo + PL."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": years,
                "datasets": [
                    {"label": "Ativo Total", "data": ativo_total, "backgroundColor": "#0d9488"},
                    {"label": "Passivo Total", "data": passivo_total, "backgroundColor": "#ef4444"},
                    {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "R$"}}},
                "plugins": {
                    "title": {"display": True, "text": "Estrutura do Balanço Patrimonial"},
                },
            },
        },
    }


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
