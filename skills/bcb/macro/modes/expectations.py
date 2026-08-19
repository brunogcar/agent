"""Mode: expectations -- BCB Focus market-expectations dashboard.

Surfaces market expectations from the BCB Focus survey (Olinda OData API)
for 4 indicators: IPCA (monthly), Selic (annual), PIB (annual), Cambio
(monthly). For each indicator, shows:
  - A chart of the median expectation over time with a min/max band.
  - A table of the latest expectations.

Charts use a dual-dataset pattern: a filled area between min + max (range)
+ a line for the median. This makes the spread of forecasts visible at a
glance -- a wide band means high uncertainty.

[v1.4] New mode registered as "expectations" in skills.bcb.macro._registry.
Reads from data_sources.bcb.focus.query_engine (read-only). Falls back
gracefully when the focus DB is not synced.
"""
from __future__ import annotations

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import format_value
from skills.bcb.macro.report import (
    build_kpi_card, build_error_section,
)

# Import the focus query_engine functions. The dashboard calls these
# module-level names so they can be monkeypatched in tests.
from data_sources.bcb.focus.query_engine import (
    expectations as query_expectations, last_value as focus_last_value,
)


# Indicator + frequency pairs to render in the dashboard (mirrors
# DEFAULT_INDICATORS in data_sources.bcb.focus.catalog).
_INDICATOR_PANELS: list[tuple[str, str, str]] = [
    # (indicador, frequency, panel title)
    ("IPCA",   "monthly", "IPCA - Expectativas Mensais"),
    ("Selic",  "annual",  "Selic - Expectativas Anuais"),
    ("Câmbio", "monthly", "Câmbio - Expectativas Mensais"),
]

# Per-indicator unit + Chart.js color (mirrors the macro palette).
_INDICATOR_META: dict[str, tuple[str, str]] = {
    "IPCA":   ("%",      "#f59e0b"),
    "Selic":  ("% a.a.", "#0d9488"),
    "Câmbio": ("R$",     "#3b82f6"),
}


def _build_indicator_chart(title: str, unit: str, color: str,
                           observations: list[dict]) -> dict:
    """Build a median + min/max band chart for one indicator.

    observations are sorted DESC by data (most recent first). We reverse
    to ascending for the chart x-axis.
    """
    asc = sorted(
        [o for o in observations if o.get("data")],
        key=lambda o: o["data"],
    )
    labels = [o["data"] for o in asc]
    medians = [o.get("mediana") for o in asc]
    mins = [o.get("minimo") for o in asc]
    maxs = [o.get("maximo") for o in asc]

    # Range band: filled area between min and max. We use two stacked
    # datasets -- the lower bound (transparent line) + the band height
    # (filled). Chart.js supports this via the standard 'fill: -1' pattern
    # but to keep it simple + robust we just plot min/max as separate
    # dashed lines + the median as a solid line.
    return {
        "type":        "chart",
        "title":       title,
        "unit":        unit,
        "description": (
            "Mediana das expectativas (linha solida) + faixa min/max "
            "(linhas tracejadas). Faixa larga = alta incerteza; faixa "
            "estreita = consenso."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Mediana",
                        "data": medians,
                        "borderColor": color,
                        "backgroundColor": color,
                        "borderWidth": 2,
                        "pointRadius": 0,
                        "pointHoverRadius": 4,
                        "tension": 0.2,
                        "fill": False,
                    },
                    {
                        "label": "Maximo",
                        "data": maxs,
                        "borderColor": "#ef4444",
                        "backgroundColor": "rgba(239,68,68,0.06)",
                        "borderWidth": 1,
                        "borderDash": [3, 3],
                        "pointRadius": 0,
                        "fill": False,
                        "tension": 0.2,
                    },
                    {
                        "label": "Minimo",
                        "data": mins,
                        "borderColor": "#22c55e",
                        "backgroundColor": "rgba(34,197,94,0.06)",
                        "borderWidth": 1,
                        "borderDash": [3, 3],
                        "pointRadius": 0,
                        "fill": False,
                        "tension": 0.2,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"title": {"display": True, "text": unit}},
                },
                "plugins": {
                    "title": {"display": True, "text": title},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": medians, "label": "Mediana"},
            {"data": maxs, "label": "Maximo"},
            {"data": mins, "label": "Minimo"},
        ],
        "price_full_data": medians,
    }


def _build_indicator_table(title: str, observations: list[dict], unit: str = "") -> dict:
    """Build a table of the latest expectations for one indicator.

    Right-aligns the numeric columns (Media, Mediana, Minimo, Maximo,
    Respondentes); left-aligns Data + Data Ref.
    """
    rows = []
    for o in observations[:15]:  # cap at 15 rows
        # Format with consistent decimals: 2 for %, 4 for R$
        _fmt = (lambda v: f"{v:.2f}" if v is not None else "-") if unit != "R$" else (lambda v: f"{v:.4f}" if v is not None else "-")
        rows.append([
            o.get("data", ""),
            o.get("data_referencia", ""),
            _fmt(o.get("media")),
            _fmt(o.get("mediana")),
            _fmt(o.get("minimo")),
            _fmt(o.get("maximo")),
            str(o.get("numero_respondentes") or "-"),
        ])
    return {
        "type":        "table",
        "title":       f"{title} - tabela",
        "description": "Ultimas expectativas registradas (top 15).",
        "columns":     ["Data", "Data Ref.", "Media", "Mediana",
                        "Minimo", "Maximo", "Resp."],
        "rows":        rows,
        # Right-align numeric columns (2-6); left-align Data + Data Ref (0-1).
        "column_align": ["left", "left", "right", "right", "right",
                         "right", "right"],
    }


@register_mode(
    "expectations",
    description=(
        "BCB Focus expectations dashboard. 4 indicators (IPCA mensal, Selic "
        "anual, PIB anual, Cambio mensal) com mediana + faixa min/max. "
        "Le de data_sources.bcb.focus (Olinda OData)."
    ),
    params={
        "limit": "int. Max expectations per indicator. Default: 50.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="expectations")',
        'skill(domain="bcb", sub_domain="macro", mode="expectations", '
        'params=\'{"limit":30}\')',
    ],
)
def expectations(limit: int = 50) -> dict:
    """Build the Focus expectations dashboard."""
    sections: list[dict] = []
    kpis: list[dict] = []

    for indicador, frequency, title in _INDICATOR_PANELS:
        unit, color = _INDICATOR_META.get(indicador, ("", "#0d9488"))
        res = query_expectations(indicador=indicador, frequency=frequency,
                                 limit=limit)
        if res.get("status") != "ok":
            sections.append(build_error_section(
                title, res.get("error", "sem dados")))
            kpis.append(build_kpi_card(
                f"{indicador} (mediana)", None, unit))
            continue

        observations = res.get("observations", [])
        if not observations:
            sections.append(build_error_section(
                title, "sem observacoes"))
            kpis.append(build_kpi_card(
                f"{indicador} (mediana)", None, unit))
            continue

        # KPI: latest median.
        latest = observations[0]  # already sorted DESC by data
        kpis.append(build_kpi_card(
            f"{indicador} (mediana)",
            latest.get("mediana"),
            unit,
            subtitle=(
                f"ref: {latest.get('data_referencia', '')} | "
                f"resp: {latest.get('numero_respondentes', '-')}"
            ),
        ))

        sections.append(_build_indicator_chart(title, unit, color, observations))
        sections.append(_build_indicator_table(title, observations, unit))

    return {
        "status":   "ok",
        "mode":     "expectations",
        "kpis":     kpis,
        "sections": sections,
    }
