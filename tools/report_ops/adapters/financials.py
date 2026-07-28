"""adapters/financials.py — Flatten financials skill JSON → table + chart data.

Adapters:
  financials_quarterly         — quarterly summary table (newest-first) + KPIs
  financials_annual            — annual summary table (newest-first) + KPIs
  financials_summary           — KPIs + quarterly trend table + latest-annual detail
  financials_quarterly_chart   — multi-series line chart of Receita, EBITDA,
                                 Lucro Líquido over time (standalone quarters)

The financials skill returns periods with nested {metrics, ratios}. The table
adapters pivot that into a wide table (one row per period, columns = metrics +
ratios) with per-column format specs so HTML and xlsx render consistently.

The chart adapter produces the multi-series chart data shape:
    {"x": ["1T26","4T25",...], "datasets": [{"label":"Receita","data":[...]}, ...]}

which charts._to_chartjs_config() renders as one line per metric.

File history: financials_chart.py was merged into this file (preserved via
the original financials.py path; financials_chart.py was deleted).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _kv_section, _safe_num,
)


# Money metrics shown as compact BRL; ratio columns as % (fractions).
_MONEY_COLS = ["Receita Líquida", "Lucro Bruto", "EBIT", "EBITDA",
               "Lucro Líquido", "FCO"]
_RATIO_COLS_Q = ["Marg. Bruta", "Marg. EBITDA", "Marg. Líquida", "ROE"]
_RATIO_COLS_A = ["Marg. Bruta", "Marg. EBITDA", "Marg. Líquida", "ROE", "ROA", "Payout"]

_METRIC_KEY = {
    "Receita Líquida": "receita_liquida",
    "Lucro Bruto": "lucro_bruto",
    "EBIT": "ebit",
    "EBITDA": "ebitda",
    "Lucro Líquido": "lucro_liquido",
    "FCO": "fco",
}
_RATIO_KEY = {
    "Marg. Bruta": "marg_bruta",
    "Marg. EBITDA": "marg_ebitda",
    "Marg. Líquida": "marg_liquida",
    "ROE": "roe",
    "ROA": "roa",
    "Payout": "payout",
}


# Metrics to plot — each becomes one line. (label, metrics_key)
# Money metrics only (all BRL) so the y-axis is consistent.
# (Used by the financials_quarterly_chart adapter — was previously in
# financials_chart.py before the merge.)
_CHART_METRICS = [
    ("Receita Líquida",  "receita_liquida"),
    ("EBITDA",           "ebitda"),
    ("Lucro Líquido",    "lucro_liquido"),
]


def _formats_for(columns: list[str]) -> dict:
    """Map each column name to its format spec."""
    f = {"Período": "text"}
    for c in _MONEY_COLS:
        if c in columns:
            f[c] = "brl"
    for c in _RATIO_COLS_Q + _RATIO_COLS_A:
        if c in columns:
            f[c] = "pct"
    return f


def _summary_section(periods: list[dict], is_quarterly: bool) -> dict:
    """Build the wide summary table section from a periods list.

    quarterly periods come oldest-first from the skill; we reverse to newest-first.
    annual periods are already newest-first.
    """
    cols = ["Período"] + _MONEY_COLS + (_RATIO_COLS_Q if is_quarterly else _RATIO_COLS_A)
    ordered = list(reversed(periods)) if is_quarterly else list(periods)

    rows = []
    for p in ordered:
        m = p.get("metrics", {}) or {}
        r = p.get("ratios", {}) or {}
        label = p.get("period") or p.get("data_fim_exerc") or ""
        row = [label]
        for c in _MONEY_COLS:
            row.append(_safe_num(m.get(_METRIC_KEY[c])))
        ratio_cols = _RATIO_COLS_Q if is_quarterly else _RATIO_COLS_A
        for c in ratio_cols:
            row.append(_safe_num(r.get(_RATIO_KEY[c])))
        rows.append(row)

    return {
        "title": "Quarterly Summary" if is_quarterly else "Annual Summary",
        "columns": cols,
        "rows": rows,
        "formats": _formats_for(cols),
        "note": "Standalone quarters derived from ITR cumulative + DFP annual." if is_quarterly
                else "Annual values from DFP (meses=12) + DVA.",
    }


def _kpis_from_period(p: dict) -> list[dict]:
    """Build KPI cards from the latest period's metrics + ratios."""
    m = p.get("metrics", {}) or {}
    r = p.get("ratios", {}) or {}
    return [
        {"label": "Receita Líquida", "value": _safe_num(m.get("receita_liquida")), "format": "brl"},
        {"label": "EBITDA", "value": _safe_num(m.get("ebitda")), "format": "brl"},
        {"label": "Lucro Líquido", "value": _safe_num(m.get("lucro_liquido")), "format": "brl"},
        {"label": "Marg. EBITDA", "value": _safe_num(r.get("marg_ebitda")), "format": "pct"},
    ]


def _detail_section(p: dict) -> dict:
    """Key-value breakdown of a single period's metrics (latest annual detail)."""
    m = p.get("metrics", {}) or {}
    rows = [
        ("Ativo Total", _safe_num(m.get("ativo_total")), "brl"),
        ("Caixa e Equivalentes", _safe_num(m.get("caixa")), "brl"),
        ("Patrimônio Líquido", _safe_num(m.get("patrimonio_liquido")), "brl"),
        ("Dívida Bruta", _safe_num(m.get("divida_bruta")), "brl"),
        ("Receita Líquida", _safe_num(m.get("receita_liquida")), "brl"),
        ("Lucro Bruto", _safe_num(m.get("lucro_bruto")), "brl"),
        ("EBIT", _safe_num(m.get("ebit")), "brl"),
        ("EBITDA", _safe_num(m.get("ebitda")), "brl"),
        ("Lucro Líquido", _safe_num(m.get("lucro_liquido")), "brl"),
        ("FCO", _safe_num(m.get("fco")), "brl"),
        ("FCI", _safe_num(m.get("fci")), "brl"),
        ("FCF", _safe_num(m.get("fcf")), "brl"),
        ("D&A", _safe_num(m.get("da")), "brl"),
        ("Proventos (DVA)", _safe_num(m.get("proventos")), "brl"),
    ]
    label = p.get("period") or p.get("data_fim_exerc") or "Latest"
    sec = _kv_section(f"Latest Annual Detail ({label})", rows)
    sec["note"] = f"EBITDA method: {m.get('ebitda_method', 'unknown')}"
    return sec


@register_adapter("financials_quarterly")
def quarterly(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Quarterly Financials")
    periods = result.get("periods") or []
    if not periods:
        return _error_table(result, title="Quarterly Financials")
    return {
        "company": result.get("company", ""),
        "sections": [_summary_section(periods, is_quarterly=True)],
        "kpis": _kpis_from_period(periods[-1]),  # newest (periods are oldest-first)
        "sources": [],
    }


@register_adapter("financials_annual")
def annual(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Annual Financials")
    periods = result.get("periods") or []
    if not periods:
        return _error_table(result, title="Annual Financials")
    return {
        "company": result.get("company", ""),
        "sections": [_summary_section(periods, is_quarterly=False)],
        "kpis": _kpis_from_period(periods[0]),  # newest (annual is newest-first)
        "sources": [],
    }


@register_adapter("financials_summary")
def summary(result: dict) -> dict:
    """Combined: KPIs (latest annual) + quarterly trend + latest-annual detail."""
    if not _ok(result):
        return _error_table(result, title="Financials Summary")

    sections_ = result.get("sections") or {}
    company = result.get("company", "")
    kpis: list[dict] = []
    out_sections: list[dict] = []

    latest_annual = sections_.get("latest_annual") or {}
    if latest_annual.get("status") == "ok" or latest_annual.get("metrics"):
        kpis = _kpis_from_period(latest_annual)
        out_sections.append(_detail_section(latest_annual))

    trend = sections_.get("quarterly_trend") or []
    if isinstance(trend, list) and trend:
        out_sections.append(_summary_section(trend, is_quarterly=True))
    else:
        lq = sections_.get("latest_quarterly") or {}
        if lq.get("status") == "ok" or lq.get("metrics"):
            out_sections.append(_summary_section([lq], is_quarterly=True))

    if not out_sections:
        return _error_table(result, title="Financials Summary")

    return {
        "company": company,
        "sections": out_sections,
        "kpis": kpis,
        "sources": [],
    }


# ── financials_quarterly_chart adapter ─────────────────────────────────────
# (Merged from financials_chart.py — preserves the multi-series chart shape.)

@register_adapter("financials_quarterly_chart")
def quarterly_chart(result: dict) -> dict:
    """Flatten financials.quarterly result into multi-series chart data.

    Produces: {"x": [period labels oldest-first], "datasets": [{label, data}]}
    so charts.build() renders a multi-line trend chart.
    """
    if not _ok(result):
        # Return a minimal error shape that the chart builder can render
        return {"x": [], "y": [], "_error": _error_table(result, title="Financials Chart")}

    periods = result.get("periods") or []
    if not periods:
        return {"x": [], "y": [], "_error": _error_table(result, title="Financials Chart")}

    # Sort oldest-first for a left-to-right timeline
    sorted_p = sorted(periods,
                      key=lambda p: (p.get("year", 0), p.get("quarter", 0)))
    x_labels = [p.get("period", "?") for p in sorted_p]

    datasets = []
    for label, key in _CHART_METRICS:
        data = []
        for p in sorted_p:
            m = p.get("metrics") or {}
            v = m.get(key)
            data.append(v if v is not None else None)
        datasets.append({"label": label, "data": data})

    return {"x": x_labels, "datasets": datasets}
