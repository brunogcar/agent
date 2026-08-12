"""report/efficiency.py — Efficiency & Growth tab builder.

Contains:
  - build_efficiency_growth_sections — Efficiency Ratios table + 3 Growth
    tables (3M / 1Y / 5Y) grouped by time horizon + per-horizon bar charts.
    Falls back to computing growth from annual_periods when ratios_dict
    growth metrics are None.
"""
from __future__ import annotations

from skills.cvm.valuation.report._helpers import _safe_get, _fmt
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


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
