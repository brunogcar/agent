"""adapters/financials_dashboard.py — Financials dashboard adapter.

Takes a financials.dashboard() result and produces a multi-tab dashboard
payload for the report tool's dashboard action.

Usage:
  report(action="dashboard", data=<financials dashboard result>,
         config={"adapter": "financials_dashboard"})

The financials.dashboard() function already shapes the data into tabs:
  - Overview: KPI cards (Receita, EBITDA, Lucro Líquido, Margem EBITDA, ROE,
    Dívida Líquida/EBITDA) + freshness metadata
  - DRE: latest annual income-statement metrics + 4-quarter trend
  - Balanço: latest annual ativo (caixa + ativo_total) + passivo (PL +
    dívida bruta + dívida líquida)
  - DFC: latest annual cash flows (FCO/FCI/FCF) + 4-quarter trend
  - Ratios: categorized ratio grid (profitability/liquidity/leverage/
    efficiency/growth/tax) via compute_all_ratios()

This adapter is THIN — the dashboard function already produces the tab
structure. The adapter only:
  1. Pulls Overview tab's KPIs to the top-level `kpis` field (with BRL /
     pct / num / x formatting based on each KPI's `unit`).
  2. Converts the financials-internal section shapes (latest_annual with
     metrics dict, quarterly_trend with periods list, ratio_grid with
     categories dict) into the dashboard template's expected section
     shapes (type="table" with columns/rows, type="ratio_grid" with
     categories list of {label, items}).
  3. Drops the metadata-only sections (latest_annual with just a period,
     latest_quarterly with just a period, kpis section that mirrors the
     tab.kpis).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)


# ── KPI formatting ───────────────────────────────────────────────────────────
# Each financials.dashboard() KPI carries a `unit` ("BRL", "ratio", "x") that
# tells us how to format the value. Map each unit to a format spec understood
# by tools.report_ops.formats.apply_fmt().

_UNIT_TO_SPEC = {
    "BRL":   "brl",       # Compact BRL with B/T/M suffixes
    "ratio": "pct",       # Fraction -> percentage
    "x":     "num",       # Multiplier (2 decimals, no % sign)
    "num":   "num",
    "int":   "int",
}


def _format_kpi(k: dict) -> dict:
    """Convert a financials.dashboard() KPI into a formatted KPI card.

    Input:  {"label": "Receita Líquida", "value": 100000, "unit": "BRL"}
    Output: {"label": "Receita Líquida", "value": "R$ 100 mil", "format": "brl"}

    [v1.12] The dashboard mode now pre-formats KPI values as strings via
    `apply_fmt` in skills/cvm/financials/report.py (so the value is ready
    for direct display). When the value is already a string, pass it
    through verbatim — re-running apply_fmt on a pre-formatted string
    would yield "—" because the string can't be coerced to float. Only
    raw numbers (legacy callers + the synthetic test data with raw
    numeric values) get re-formatted via the unit→spec map.
    """
    from tools.report_ops.formats import apply_fmt
    label = k.get("label", "")
    value = k.get("value")
    unit = (k.get("unit") or "").strip()
    spec = _UNIT_TO_SPEC.get(unit, "text")

    if isinstance(value, str):
        formatted = value
    else:
        try:
            formatted = apply_fmt(_safe_num(value), spec)
        except Exception:
            formatted = str(value) if value is not None else "—"

    return {
        "label": label,
        "value": formatted,
        "format": spec,
    }


# ── Section converters ───────────────────────────────────────────────────────
# Each financials.dashboard() section has a `name` that identifies its shape.
# Convert each into the dashboard template's section format.

# Pretty labels for the metric keys used in the DRE + Balanço + DFC tabs.
_DRE_METRIC_LABELS = [
    ("receita_liquida",      "Receita Líquida",      "brl"),
    ("lucro_bruto",          "Lucro Bruto",          "brl"),
    ("ebit",                 "EBIT",                 "brl"),
    ("ebitda",               "EBITDA",               "brl"),
    ("resultado_financeiro", "Resultado Financeiro", "brl"),
    ("lucro_liquido",        "Lucro Líquido",        "brl"),
    ("da",                   "D&A",                  "brl"),
]
_DRE_RATIO_LABELS = [
    ("marg_bruta",   "Marg. Bruta",   "pct"),
    ("marg_ebit",    "Marg. EBIT",    "pct"),
    ("marg_ebitda",  "Marg. EBITDA",  "pct"),
    ("marg_liquida", "Marg. Líquida", "pct"),
]
_BALANCO_ATIVO_LABELS = [
    ("ativo_total", "Ativo Total", "brl"),
    ("caixa",       "Caixa",       "brl"),
]
_BALANCO_PASSIVO_LABELS = [
    ("patrimonio_liquido", "Patrimônio Líquido", "brl"),
    ("divida_bruta",       "Dívida Bruta",       "brl"),
    ("divida_liquida",     "Dívida Líquida",     "brl"),
]
_DFC_METRIC_LABELS = [
    ("fco", "FCO", "brl"),
    ("fci", "FCI", "brl"),
    ("fcf", "FCF", "brl"),
]

# Quarterly trend column specs (period + 3 metric columns).
_DRE_TREND_COLS = [
    ("period",        "Período",      "text"),
    ("receita",       "Receita",      "brl"),
    ("ebitda",        "EBITDA",       "brl"),
    ("lucro_liquido", "Lucro Líquido","brl"),
]
_DFC_TREND_COLS = [
    ("period", "Período", "text"),
    ("fco",    "FCO",     "brl"),
    ("fci",    "FCI",     "brl"),
    ("fcf",    "FCF",     "brl"),
]

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

# Metrics whose values are ratios (display as pct); everything else displays as num.
_RATIO_PCT_KEYS = {
    "roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin",
    "ebitda_margin", "ocf_margin", "fcf_margin",
    "debt_equity", "cash_flow_to_debt", "capex_revenue",
    "retention_ratio", "sustainable_growth",
    "dpa", "effective_tax_rate",
}


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


def _trend_table_section(title: str, periods: list[dict],
                         cols: list[tuple[str, str, str]]) -> dict:
    """Build a trend table section: one row per period, columns per `cols`."""
    from tools.report_ops.formats import apply_fmt
    columns = [label for _key, label, _spec in cols]
    rows = []
    for p in periods or []:
        row = []
        for key, _label, spec in cols:
            v = p.get(key)
            if spec == "text":
                row.append(v if v is not None else "")
            else:
                row.append(apply_fmt(_safe_num(v), spec))
        rows.append(row)
    return {
        "title": title,
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": {c: "text" for c in columns},  # already pre-formatted above
        "note": "Períodos ordenados do mais recente para o mais antigo." if rows
                else "Sem dados disponíveis.",
    }


def _ratio_grid_section(title: str, categories: dict) -> dict:
    """Build a ratio_grid section from the financials.dashboard() categories dict.

    Input categories dict shape:
        {"profitability": {"roe": 0.15, "roa": 0.08, ...}, ...}

    Output ratio_grid section shape (consumed by macros.ratio_grid):
        {"type": "ratio_grid", "categories": [
            {"label": "Rentabilidade", "items": [
                {"label": "ROE", "value": "15,00%"},
                {"label": "ROA", "value": "8,00%"},
                ...
            ]}, ...
        ]}
    """
    from tools.report_ops.formats import apply_fmt

    cats_out = []
    for cat_name in sorted(categories.keys()):
        metrics = categories[cat_name] or {}
        if not isinstance(metrics, dict):
            continue
        items = []
        for metric_name in sorted(metrics.keys()):
            value = metrics.get(metric_name)
            spec = "pct" if metric_name in _RATIO_PCT_KEYS else "num"
            label = _METRIC_LABELS.get(metric_name, metric_name)
            items.append({
                "label": label,
                "value": apply_fmt(_safe_num(value), spec),
            })
        if not items:
            continue
        cat_label = _RATIO_CATEGORY_LABELS.get(cat_name, cat_name.capitalize())
        cats_out.append({"label": cat_label, "items": items})

    return {
        "title": title,
        "type": "ratio_grid",
        "categories": cats_out,
    }


def _convert_section(sec: dict) -> list[dict]:
    """Convert one financials.dashboard() section into 0+ dashboard sections.

    Dispatches on `sec["name"]`:
      - "kpis":             skip (mirrors top-level kpis)
      - "latest_annual":    dispatch on inner shape (metrics? ativo? passivo?)
      - "latest_quarterly": skip (metadata-only)
      - "freshness":        convert to a small key-value table
      - "quarterly_trend":  convert to a trend table
      - "ratio_grid":       convert to a ratio_grid section
    """
    if not isinstance(sec, dict):
        return []
    name = sec.get("name", "")

    if name == "kpis":
        # KPIs are pulled to top-level; skip in tab.sections.
        return []

    if name == "freshness":
        data = sec.get("data") or {}
        if not isinstance(data, dict) or not data:
            return []
        rows = []
        for db_name in sorted(data.keys()):
            info = data[db_name]
            if isinstance(info, dict):
                rows.append([db_name, str(info.get("last_updated", "—"))])
            else:
                rows.append([db_name, str(info)])
        return [{
            "title": "Data Freshness",
            "type": "table",
            "columns": ["Database", "Last Updated"],
            "rows": rows,
            "formats": {"Database": "text", "Last Updated": "text"},
        }]

    if name == "quarterly_trend":
        # DRE and DFC tabs both have a quarterly_trend section. Detect which
        # one by inspecting the first period's keys.
        periods = sec.get("periods") or []
        if not periods:
            return []
        first = periods[0] if periods else {}
        if "receita" in first or "ebitda" in first or "lucro_liquido" in first:
            return [_trend_table_section("Quarterly Trend (DRE)", periods, _DRE_TREND_COLS)]
        if "fco" in first or "fci" in first or "fcf" in first:
            return [_trend_table_section("Quarterly Trend (DFC)", periods, _DFC_TREND_COLS)]
        # Unknown shape — fall back to a generic table with all keys.
        return [_trend_table_section("Quarterly Trend", periods,
                                     [(k, k.capitalize(), "text") for k in first.keys()])]

    if name == "ratio_grid":
        cats = sec.get("categories") or {}
        return [_ratio_grid_section("Ratios by Category", cats)]

    if name == "latest_annual":
        # Dispatch on inner shape: DRE has metrics + ratios, Balanço has
        # ativo + passivo, DFC has metrics only.
        if "ativo" in sec or "passivo" in sec:
            out = []
            ativo = sec.get("ativo") or {}
            passivo = sec.get("passivo") or {}
            if ativo:
                out.append(_kv_table_section(
                    "Ativo (Latest Annual)",
                    [(k, ativo.get(k), spec) for k, _l, spec in _BALANCO_ATIVO_LABELS
                     if k in ativo]
                    or [(k, ativo.get(k), spec) for k, _l, spec in _BALANCO_ATIVO_LABELS]))
            if passivo:
                out.append(_kv_table_section(
                    "Passivo (Latest Annual)",
                    [(k, passivo.get(k), spec) for k, _l, spec in _BALANCO_PASSIVO_LABELS
                     if k in passivo]
                    or [(k, passivo.get(k), spec) for k, _l, spec in _BALANCO_PASSIVO_LABELS]))
            return out
        # DRE or DFC: both have a `metrics` dict; DRE also has `ratios`.
        metrics = sec.get("metrics") or {}
        ratios = sec.get("ratios") or {}
        out = []
        if metrics:
            # Detect DRE vs DFC by key set.
            if "receita_liquida" in metrics or "lucro_liquido" in metrics:
                out.append(_kv_table_section(
                    "DRE (Latest Annual)",
                    [(k, metrics.get(k), spec) for k, _l, spec in _DRE_METRIC_LABELS]))
            else:
                out.append(_kv_table_section(
                    "DFC (Latest Annual)",
                    [(k, metrics.get(k), spec) for k, _l, spec in _DFC_METRIC_LABELS]))
        if ratios:
            out.append(_kv_table_section(
                "Margins (Latest Annual)",
                [(k, ratios.get(k), spec) for k, _l, spec in _DRE_RATIO_LABELS]))
        return out

    if name == "latest_quarterly":
        # Just a period string — metadata only, skip.
        return []

    # Unknown section shape — pass through as a text block.
    # But if the section already has a "type" field (new report.py format),
    # pass it through as-is — it's already in the correct dashboard shape.
    if sec.get("type"):
        return [sec]
    return [{
        "title": name,
        "type": "text",
        "text": f"Section '{name}' shape not recognized by financials_dashboard adapter.",
    }]


# ── Adapter entry point ──────────────────────────────────────────────────────

@register_adapter("financials_dashboard")
def financials_dashboard(result: dict) -> dict:
    """Flatten financials.dashboard() result into a multi-tab dashboard payload."""
    if not _ok(result):
        return _error_table(result, title="Financials Dashboard")

    tabs_in = result.get("tabs") or []
    if not tabs_in:
        return _error_table(result, title="Financials Dashboard")

    # Pull KPIs from top-level result["kpis"] (new format) or from
    # Overview tab's "kpis" key (old format).
    kpis: list[dict] = []
    top_kpis = result.get("kpis") or []
    if top_kpis:
        for k in top_kpis:
            kpis.append(_format_kpi(k))
    else:
        for tab in tabs_in:
            if tab.get("name") == "Overview":
                for k in tab.get("kpis") or []:
                    kpis.append(_format_kpi(k))
                break

    # Convert each tab's sections into the dashboard template format.
    tabs_out: list[dict] = []
    for tab in tabs_in:
        sections_out: list[dict] = []
        for sec in tab.get("sections") or []:
            sections_out.extend(_convert_section(sec))
        tabs_out.append({
            "name": tab.get("name", ""),
            "sections": sections_out,
        })

    return {
        "company": result.get("company", ""),
        "tabs": tabs_out,
        "kpis": kpis,
        "sources": [],
    }
