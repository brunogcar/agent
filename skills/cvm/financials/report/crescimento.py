"""skills/cvm/financials/report/crescimento.py -- Crescimento tab builders.

Builds the Crescimento tab (growth ratio_grid + 3M/1Y/5Y table + per-metric
bar charts). Growth values are pulled from ``ratios_payload`` (computed by
``compute_all_ratios`` with the FIXED growth_at anchoring).

Public builder:
  - ``build_crescimento_sections(...)`` — top-level sections for the tab.

Private helpers:
  - ``_period_date(p)`` — extract YYYY-MM-DD date from an annual period dict.
  - ``_build_metric_periods(annual_periods, metric_key)`` — builds a list of
    ``{"date": str, "value": float|None}`` entries sorted oldest-first.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt
from skills.cvm.financials.report.indicadores import (
    _build_growth_ratio_grid_section,
)


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
        "negative_red": True,
        "positive_green": True,
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
    # [v24] Different color per metric, with shades for 3M/1Y/5Y
    # Receita Líquida: teal shades (light → dark)
    # Lucro Bruto: orange shades
    # Lucro Líquido: purple shades
    _METRIC_COLORS = {
        "Receita Líquida": ["#5eead4", "#14b8a6", "#0f766e"],  # teal: 3M light, 1Y mid, 5Y dark
        "Lucro Bruto":     ["#fdba74", "#f97316", "#c2410c"],  # orange
        "Lucro Líquido":   ["#d8b4fe", "#a855f7", "#7e22ce"],  # purple
    }

    def _metric_chart(
        metric_label: str, vals: list[float | None],
    ) -> dict | None:
        """Build a single-metric 3-bar chart (3M / 1A / 5Y) with shaded colors."""
        if all(v is None for v in vals):
            return None
        labels = ["3M", "1A", "5A"]
        data = [(v * 100 if v is not None else None) for v in vals]
        colors = _METRIC_COLORS.get(metric_label, ["#a855f7", "#22c55e", "#3b82f6"])
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
                        "backgroundColor": colors,
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
                        "legend": {
                            "display": False,
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
