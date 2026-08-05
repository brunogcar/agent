"""skills/b3/index/helpers.py -- Helpers for B3 index skill."""
from __future__ import annotations


def format_pct(value) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}%"


def format_qty(value) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def build_constituent_table(constituents: list[dict], limit: int = 0) -> dict:
    """Build a table section from constituents list."""
    rows = constituents
    if limit > 0:
        rows = rows[:limit]
    return {
        "type": "table",
        "title": f"Top {len(rows)} Constituents",
        "columns": ["Rank", "Ticker", "Company", "Type", "Qty", "Part. %"],
        "rows": [[c.get("rank", ""), c["ticker"], c.get("company_name", ""),
                  c.get("type", ""), format_qty(c.get("theorical_qty")),
                  format_pct(c.get("participation"))] for c in rows],
    }


def build_chart_section(title: str, constituents: list[dict],
                        description: str = "") -> dict:
    """Build a bar chart of top constituents by participation.

    chart_data must be a full Chart.js config object (not a list of {x,y})
    because the dashboard template passes it directly to new Chart().
    """
    top = sorted(constituents, key=lambda c: c.get("participation") or 0, reverse=True)[:15]
    labels = [c["ticker"] for c in top]
    data = [c.get("participation") or 0 for c in top]
    return {
        "type": "chart",
        "chart_type": "bar",
        "title": title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Participacao (%)",
                    "data": data,
                    "backgroundColor": "rgba(13, 148, 136, 0.7)",
                    "borderColor": "rgba(13, 148, 136, 1)",
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {"display": True, "text": title},
                    "legend": {"display": False},
                },
                "scales": {
                    "y": {"beginAtZero": True, "title": {"display": True, "text": "%"}},
                    "x": {"ticks": {"maxRotation": 45, "minRotation": 45}},
                },
            },
        },
    }
