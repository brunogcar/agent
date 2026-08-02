"""skills/cvm/_shared_report/price_chart.py — Historical price chart builder.

[v1.16.1] Extracted from skills/cvm/financials/report.py so all CVM skills
can reuse the same historical price chart with time-range selector.

Builds a line chart section with Tudo/5A/1A/1M range selector buttons.
The filtering is done client-side via filterPriceChart() JS in dashboard.html.
"""
from __future__ import annotations


def build_price_chart(company: str) -> dict | None:
    """Build a historical price chart section with time-range selector.

    Fetches the full available price history from COTAHIST (last 10 years)
    and returns a chart section. The time-range selector (All / 5Y / 1Y /
    1M) is implemented client-side via JS buttons that filter the dataset.

    Returns None if no price data is available.
    """
    try:
        from skills.cvm.calculations.engines.price import price_series
        from datetime import date, timedelta
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 10)).isoformat()
    date_to = today.isoformat()

    try:
        series = price_series(company, date_from, date_to)
    except Exception:
        return None

    if not series or len(series) < 2:
        return None

    labels = [p.get("date", "") for p in series]
    closes = [p.get("close") for p in series]

    return {
        "type": "chart",
        "title": f"Cotação Histórica — {company}",
        "description": (
            "Preço de fechamento diário. Use os botões para selecionar o "
            "período: Tudo / 5A / 1A / 1M."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": f"{company} — Fechamento (R$)",
                    "data": closes,
                    "borderColor": "#0d9488",
                    "backgroundColor": "rgba(13,148,136,0.1)",
                    "fill": True,
                    "tension": 0.1,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$"}},
                },
                "plugins": {
                    "title": {"display": True, "text": f"Cotação Histórica — {company}"},
                    "legend": {"display": False},
                },
            },
        },
        # Custom field consumed by dashboard.html to render the
        # time-range selector buttons above the chart.
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_data": closes,
    }
