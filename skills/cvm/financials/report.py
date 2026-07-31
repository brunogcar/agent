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

    # Freshness (best-effort — only if the freshness module is importable)
    try:
        from skills.cvm._freshness import get_freshness, get_last_synced_period
        fresh = get_freshness()
        last = get_last_synced_period()
        fresh_rows = [[k, str(v)] for k, v in sorted(fresh.items())]
        last_rows = [[k, str(v)] for k, v in sorted(last.items())]
        sections.append({
            "title": "Data Freshness (sync timestamps)",
            "type": "table",
            "columns": ["Database", "Last Sync"],
            "rows": fresh_rows,
        })
        sections.append({
            "title": "Last Synced Period (data_fim_exerc)",
            "type": "table",
            "columns": ["Database", "Last Period"],
            "rows": last_rows,
        })
    except Exception:
        pass
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
    "ev_ebitda": "EV/EBITDA", "ev_fcf": "EV/FCF", "ev_sales": "EV/Sales",
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


def build_indicadores_section(today: str, ratios_payload: dict) -> dict:
    """Build the Indicadores tab as a ``type: "subtabs"`` section.

    [v1.13 review-fix] Previously this returned a single ``ratio_grid``
    with all 7 categories as cards on one canvas — visually dense and
    hard to scan.  Now each category becomes its OWN sub-tab, each
    carrying a single-category ``ratio_grid``:

      Valuation | Rentabilidade | Liquidez | Endividamento |
      Eficiência | Crescimento | Tributos

    Falls back to a single "Indicadores" sub-tab with a flat key-value
    ratio_grid if the calculations registry is unavailable.
    """
    sub_tabs: list[dict] = []
    try:
        from skills.cvm.calculations._registry import (
            METRICS, list_metrics_by_category,
        )

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
                items.append({
                    "label": label,
                    "value": _fmt(value, fmt_spec),
                })
            if items:
                cat_label = _RATIO_CATEGORY_LABELS.get(
                    category, category.capitalize())
                sub_tabs.append({
                    "name": cat_label,
                    "sections": [{
                        "title": f"{cat_label} (as of {today})",
                        "type": "ratio_grid",
                        "categories": [{"label": cat_label, "items": items}],
                    }],
                })
    except Exception:
        # Fallback: flat list of (name, value) in a single sub-tab.
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
        return {
            "type": "text",
            "text": "Nenhum indicador disponível para esta empresa.",
        }

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
) -> list[dict]:
    """Build the Crescimento tab: 3M/1Y/5Y growth table + bar chart.

    [v1.7 review-fix] Growth now uses ``growth_helpers.growth_at()`` with
    period-specific gap tolerance (1.5x for 3M/1Y, 1.2x for 5Y).  This
    handles missing annual periods gracefully: if a company skipped a
    filing year, the helper finds the closest period within the tolerance
    window instead of blindly indexing ``sorted_periods[N]``.

    Growth metrics (Revenue / Gross Profit / Net Income) are derived from
    the annual periods list when available; otherwise the table shows "—"
    and the chart is skipped.  3M remains "—" in annual-only mode (no
    quarterly data available here).
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

    rows = [
        ["Receita Líquida",   "—", _fmt(rev_1y, "pct"), _fmt(rev_5y, "pct")],
        ["Lucro Bruto",       "—", _fmt(gp_1y, "pct"), _fmt(gp_5y, "pct")],
        ["Lucro Líquido",     "—", _fmt(ni_1y, "pct"), _fmt(ni_5y, "pct")],
    ]
    sections.append({
        "title": "Growth Metrics (3M / 1Y / 5Y)",
        "type": "table",
        "columns": ["Métrica", "3M", "1Y", "5Y"],
        "rows": rows,
        "note": (
            "3M growth requires quarterly data; shows '—' in annual-only mode. "
            "1Y/5Y use period-specific gap tolerance (1.5x / 1.2x) — a missed "
            "filing year is bridged if a period falls within the tolerance window."
        ),
    })

    # Bar chart: 1Y + 5Y for each metric (3M excluded — usually missing).
    chart_data_1y = [rev_1y, gp_1y, ni_1y]
    chart_data_5y = [rev_5y, gp_5y, ni_5y]
    if any(v is not None for v in chart_data_1y + chart_data_5y):
        sections.append({
            "type": "chart",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": ["Receita Líquida", "Lucro Bruto", "Lucro Líquido"],
                    "datasets": [
                        {
                            "label": "1Y",
                            "data": [(_v * 100 if _v is not None else None)
                                     for _v in chart_data_1y],
                            "backgroundColor": "#22c55e",
                        },
                        {
                            "label": "5Y",
                            "data": [(_v * 100 if _v is not None else None)
                                     for _v in chart_data_5y],
                            "backgroundColor": "#3b82f6",
                        },
                    ],
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
            "chart_data": {
                "type": "line",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {"label": "Marg. Bruta",  "data": gross,
                         "borderColor": "#22c55e", "fill": False},
                        {"label": "Marg. EBIT",   "data": operating,
                         "borderColor": "#3b82f6", "fill": False},
                        {"label": "Marg. EBITDA", "data": ebitda,
                         "borderColor": "#f59e0b", "fill": False},
                        {"label": "Marg. Líquida","data": net,
                         "borderColor": "#a855f7", "fill": False},
                    ],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "y": {"ticks": {}},
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
                        "y": {"stacked": True},
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
    # Distribution-side codes (CVM DVA 8.01 / 8.02 / 8.03 / 8.04) — we detect
    # them by the "section" field set by dva_section_for (returns "Distribuição").
    distribution_labels = {
        "8.01": "Pessoal",
        "8.02": "Governo",
        "8.03": "Credores",
        "8.04": "Acionistas",
    }
    # Walk accounts and pick up distribution-side codes by prefix.
    dist_data: list[tuple[str, float]] = []
    for codigo, acc in accounts.items():
        if (acc.get("section") == "Distribuição"
                and acc.get("valor_brl") is not None):
            # Find the canonical label by codigo prefix.
            label = "Outros"
            for prefix, lbl in distribution_labels.items():
                if codigo.startswith(prefix):
                    label = lbl
                    break
            try:
                dist_data.append((label, float(acc["valor_brl"])))
            except (TypeError, ValueError):
                pass

    if dist_data:
        # Aggregate by label (multiple codes may map to the same label).
        agg: dict[str, float] = {}
        for label, val in dist_data:
            agg[label] = agg.get(label, 0.0) + val
        labels = list(agg.keys())
        values = [agg[k] for k in labels]
        # Use absolute values for the chart (DVA distribution is positive).
        abs_values = [abs(v) for v in values]
        sections.append({
            "type": "chart",
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
