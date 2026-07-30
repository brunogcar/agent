"""skills/cvm/financials/report.py -- Dashboard composition helpers.

Produces sections with the correct shape for the dashboard template:
  {"type": "table", "title": ..., "columns": [...], "rows": [...]}

KPIs are produced separately and placed at the top level of the dashboard.
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
    net_debt_ebitda_val: float | None,
) -> list[dict]:
    """Build 6 KPI cards with pre-formatted values."""
    return [
        {"label": "Receita Líquida",     "value": _fmt(annual_metric(latest_annual_period, "receita_liquida"), "brl")},
        {"label": "EBITDA",              "value": _fmt(annual_metric(latest_annual_period, "ebitda"), "brl")},
        {"label": "Lucro Líquido",       "value": _fmt(annual_metric(latest_annual_period, "lucro_liquido"), "brl")},
        {"label": "Margem EBITDA",       "value": _fmt(annual_ratio(latest_annual_period, "marg_ebitda"), "pct")},
        {"label": "ROE",                 "value": _fmt(roe_val, "pct")},
        {"label": "Dívida Líquida/EBITDA",   "value": _fmt(net_debt_ebitda_val, "num")},
    ]


# ── Overview tab sections ────────────────────────────────────────────────────

def build_overview_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
) -> list[dict]:
    """Build Overview tab as a table of headline metrics."""
    rows = []
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
            ["Patrimonio Liq.",   _fmt(m.get("patrimonio_liquido"),"brl")],
            ["Caixa",             _fmt(m.get("caixa"),             "brl")],
            ["Divida Bruta",      _fmt(m.get("divida_bruta"),      "brl")],
            ["FCO",               _fmt(m.get("fco"),               "brl")],
            ["FCI",               _fmt(m.get("fci"),               "brl")],
        ]
    sections = [{
        "title": "Latest Annual Summary",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    }]
    # Quarterly trend table
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
    # Freshness
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


# ── DRE tab ──────────────────────────────────────────────────────────────────

def build_dre_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
) -> list[dict]:
    """Build DRE tab as a table."""
    rows = []
    if latest_annual_period:
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
    sections = [{
        "title": "DRE (Latest Annual)",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    }]
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
    return sections


# ── Balanco tab ──────────────────────────────────────────────────────────────

def build_balanco_section(latest_annual_period: dict | None) -> dict:
    """Build Balanco tab as a table."""
    rows = []
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        r = latest_annual_period.get("ratios") or {}
        rows = [
            ["Ativo Total",          _fmt(m.get("ativo_total"),        "brl")],
            ["Caixa",                _fmt(m.get("caixa"),              "brl")],
            ["Patrimonio Liquido",   _fmt(m.get("patrimonio_liquido"), "brl")],
            ["Divida Bruta",         _fmt(m.get("divida_bruta"),       "brl")],
            ["Divida Liquida",       _fmt(r.get("divida_liquida"),     "brl")],
        ]
    return {
        "title": "Balanco (Latest Annual)",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    }


# ── DFC tab ──────────────────────────────────────────────────────────────────

def build_dfc_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
) -> list[dict]:
    """Build DFC tab as a table."""
    rows = []
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        rows = [
            ["FCO",  _fmt(m.get("fco"), "brl")],
            ["FCI",  _fmt(m.get("fci"), "brl")],
            ["FCF",  _fmt(m.get("fcf"), "brl")],
        ]
    sections = [{
        "title": "DFC (Latest Annual)",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
    }]
    if quarterly_periods:
        trend_rows = []
        for p in reversed(quarterly_periods):
            m = p.get("metrics") or {}
            trend_rows.append([
                p.get("period", "—"),
                _fmt(m.get("fco"), "brl"),
                _fmt(m.get("fci"), "brl"),
                _fmt(m.get("fcf"), "brl"),
            ])
        sections.append({
            "title": "Quarterly Trend",
            "type": "table",
            "columns": ["Período", "FCO", "FCI", "FCF"],
            "rows": trend_rows,
        })
    return sections


# ── Ratios tab ───────────────────────────────────────────────────────────────

def build_ratios_section(today: str, ratios_payload: dict) -> dict:
    """Build Ratios tab as a table grouped by category."""
    rows = []
    try:
        from skills.cvm.calculations._registry import METRICS, list_metrics_by_category
        for category in ("profitability", "liquidity", "leverage",
                         "efficiency", "growth", "tax", "valuation"):
            metrics_in_cat = list_metrics_by_category(category)
            if not metrics_in_cat:
                continue
            # Category header row
            rows.append([category.upper(), ""])
            for metric_name in metrics_in_cat:
                spec = METRICS.get(metric_name)
                if not spec:
                    continue
                value = ratios_payload.get(metric_name)
                # Determine format spec
                if category in ("profitability", "growth", "tax"):
                    fmt_spec = "pct"
                elif category == "valuation":
                    fmt_spec = "num"
                elif category == "liquidity":
                    fmt_spec = "num"
                elif category == "leverage":
                    fmt_spec = "num"
                else:
                    fmt_spec = "num"
                rows.append([f"  {spec.ratio_label}", _fmt(value, fmt_spec)])
    except Exception:
        # Fallback: flat list
        for k, v in sorted(ratios_payload.items()):
            if k in ("date", "error"):
                continue
            rows.append([k, _fmt(v, "num")])

    return {
        "title": f"Ratios (as of {today})",
        "type": "table",
        "columns": ["Metric", "Value"],
        "rows": rows,
    }
