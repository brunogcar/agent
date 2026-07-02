"""report_ops/charts.py - Chart.js configuration builders.

All rendering is client-side. This module produces JSON config objects
that the Jinja2 template injects into a <canvas> element.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.report_ops.data import load_data
from tools.report_ops.paths import report_out_dir


def build(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a Chart.js chart and return HTML path."""
    data_path = config.get("data_path", "")
    loaded, err = load_data(data=data, data_path=data_path)
    if err:
        raise ValueError(err)

    chart_type = config.get("chart_type", "bar").lower()
    chart_config = _to_chartjs_config(loaded, chart_type, title, config)

    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "chart"))
    html_path = out_dir / f"{safe_title}.html"

    # Render via Jinja2 (lazy import)
    from tools.report_ops import html
    ctx = {
        "title": title,
        # Escape </script> to prevent injection when JSON is embedded in <script> tags
        # v1.4 FIX: Use raw string to avoid invalid escape sequence \/."""
        "chart_config_json": json.dumps(chart_config).replace("</", r"<\/"),
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
    }
    html.render_template("chart.html", ctx, html_path)

    return {
        "type": "chart",
        "title": title,
        "html_path": str(html_path),
        "chart_type": chart_type,
    }


def _to_chartjs_config(data: Any, chart_type: str, title: str, config: dict) -> dict:
    """Convert raw data to a Chart.js config object."""
    if isinstance(data, dict):
        labels = data.get("x", data.get("labels", []))
        values = data.get("y", data.get("values", []))
    elif isinstance(data, list):
        values = data
        labels = list(range(len(data)))
    else:
        labels, values = [], []

    color = config.get("color", config.get("accent", "#0d9488"))

    datasets = [{
        "label": title,
        "data": values,
        "backgroundColor": color + "40",  # 25% opacity hex
        "borderColor": color,
        "borderWidth": 2,
        "tension": 0.3,
    }]

    if chart_type in ("pie", "doughnut"):
        datasets[0]["backgroundColor"] = _generate_palette(len(values), color)

    return {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": datasets,
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": True, "position": "bottom"},
                "title": {"display": bool(title), "text": title},
            },
        },
    }


def _generate_palette(n: int, base: str = "") -> list:
    """Generate n distinct colors.

    The base parameter is reserved for future theming support.
    Currently uses a fixed palette with modulo cycling. When n > 10,
    colors will repeat — this is expected behavior for large datasets.
    """
    palette = [
        "#0d9488", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
        "#14b8a6", "#6366f1", "#f97316", "#ec4899", "#84cc16",
    ]
    return [palette[i % len(palette)] for i in range(n)]
