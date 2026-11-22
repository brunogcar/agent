"""skills/b3/index/helpers.py -- Helpers for B3 index skill.

[v1.1] PT-BR formatting + the doughnut/full-list redesign:
- format_pct / format_qty used to ship EN-US formats ("10.886%",
  "3,535,764,048") in a PT-BR dashboard — now comma decimals and dot
  thousands, matching every other skill's numerics.
- build_chart_section used to slice the top 15 into a BAR chart (the
  rest of the composition invisible); it now draws a DOUGHNUT with ALL
  constituents — the ring IS the composition, tooltip identifies each
  slice, and the legend is off (78+ legend entries would be a wall).
- build_constituent_table used to cap at 20 rows by default; now lists
  EVERY constituent (limit only when explicitly requested — the compare
  mode still asks for 10).
- type strings come from B3 padded ("ON      NM") — collapsed at fetch
  time since v1.1; clean_type also normalizes rows already stored.
"""
from __future__ import annotations


def format_pct(value) -> str:
    """Participation as PT-BR "10,886%" (v1.1 — was "10.886%")."""
    if value is None:
        return "-"
    return f"{value:.3f}".replace(".", ",") + "%"


def format_qty(value) -> str:
    """Quantity as PT-BR "3.535.764.048" (v1.1 — was "3,535,764,048")."""
    if value is None:
        return "-"
    return f"{value:,}".replace(",", ".")


def clean_type(value) -> str:
    """Collapse B3's padded spec strings: "ON      NM" -> "ON NM"."""
    if not value:
        return ""
    return " ".join(str(value).split())


def pie_colors(n: int) -> list[str]:
    """Deterministic, neighbor-distinct slice colors for a composition pie.

    Golden-ratio hue stepping (137.5°) spreads consecutive constituents
    around the color wheel, so the biggest slices never sit side by side
    in a near-identical hue; lightness oscillates to separate the rest.
    Stable for the same n (same ticker order -> same colors, dark and
    light themes both read against it).
    """
    out: list[str] = []
    for i in range(n):
        h = (i * 137.508) % 360.0
        l = 52.0 + (10.0 if (i % 2) else -10.0)
        out.append(f"hsl({h:.1f}, 62%, {l:.0f}%)")
    return out


def build_constituent_table(constituents: list[dict], limit: int = 0) -> dict:
    """Build a table section from constituents list.

    [v1.1] limit=0 (the default) lists EVERY constituent — the dashboard
    used to cap at 20 while the composition has up to 136. Callers that
    want a preview (compare mode) pass an explicit limit.
    """
    rows = constituents
    if limit > 0:
        rows = rows[:limit]
        title = f"Top {len(rows)} Constituintes"
    else:
        title = f"Todos os Constituintes ({len(rows)})"
    return {
        "type": "table",
        "title": title,
        "columns": ["Rank", "Ticker", "Company", "Type", "Qty", "Part. %"],
        "rows": [[c.get("rank", ""), c["ticker"], c.get("company_name", ""),
                  clean_type(c.get("type")), format_qty(c.get("theorical_qty")),
                  format_pct(c.get("participation"))] for c in rows],
    }


def build_chart_section(title: str, constituents: list[dict],
                        description: str = "") -> dict:
    """Build a DOUGHNUT chart of the FULL composition by participation.

    [v1.1] Was a bar chart of the top 15 — every other constituent was
    invisible and the bar heights said nothing about the whole. The
    doughnut carries ALL constituents (one slice each, rank order),
    tooltip identifies each slice, and the legend is off: with 78-136
    slices the legend is a wall of labels — the full sortable table
    right below the chart is the legend. chart_data must be a full
    Chart.js config object (the dashboard template passes it directly
    to new Chart()).
    """
    ordered = sorted(constituents,
                     key=lambda c: c.get("participation") or 0, reverse=True)
    labels = [c["ticker"] for c in ordered]
    data = [c.get("participation") or 0 for c in ordered]
    return {
        "type": "chart",
        "chart_type": "doughnut",
        "title": title,
        "description": description,
        "chart_data": {
            "type": "doughnut",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Participacao (%)",
                    "data": data,
                    "backgroundColor": pie_colors(len(ordered)),
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "cutout": "45%",
                "plugins": {
                    "title": {"display": True, "text": title},
                    "legend": {"display": False},
                    "tooltip": {"enabled": True},
                },
            },
        },
    }
