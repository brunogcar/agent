"""report_ops/charts.py - Chart.js configuration builders.

All rendering is client-side. This module produces JSON config objects
that the Jinja2 template injects into a <canvas> element.

Supports three data shapes:
  1. Single-series: {"x": [...], "y": [...]}
  2. Multi-series (v1.2.2): {"x": [...], "datasets": [{"label":"A","data":[...]}, ...]}
  3. Candlestick (v1.2.6): {"_candlestick": True, "ohlc_data": [{"t","o","h","l","c"}, ...]}
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
    """Build a Chart.js chart and return HTML path.

    Supports an optional config["adapter"] that flattens a skill result into
    chart-ready data (see tools/report_ops/adapters/).
    """
    # Apply adapter if requested (flattens a skill result into chart data)
    adapter = (config.get("adapter") or "").strip()
    if adapter:
        from tools.report_ops.adapters import apply_adapter
        data = apply_adapter(adapter, data)

    data_path = config.get("data_path", "")
    loaded, err = load_data(data=data, data_path=data_path)
    if err:
        raise ValueError(err)

    chart_type = config.get("chart_type", "bar").lower()
    chart_config = _to_chartjs_config(loaded, chart_type, title, config)

    # [v1.2.8] Extract tooltip labels from candlestick config (can't be in JSON)
    tooltip_labels = chart_config.pop("_tooltip_labels", None)

    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "chart"))
    html_path = out_dir / f"{safe_title}.html"

    # Render via Jinja2 (lazy import)
    from tools.report_ops import html
    ctx = {
        "title": title,
        "chart_config_json": json.dumps(chart_config).replace("</", r"<\/"),
        "chart_type": chart_type,
        "tooltip_labels_json": json.dumps(tooltip_labels).replace("</", r"<\/") if tooltip_labels else "null",
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
    """Convert raw data to a Chart.js config object.

    Supports three data shapes:
      1. Single-series (backward-compatible): {"x": [...], "y": [...]}
      2. Multi-series (v1.2.2): {"x": [...], "datasets": [{"label":"A","data":[...]}, ...]}
      3. Candlestick (v1.2.6): {"_candlestick": True, "ohlc_data": [{"t","o","h","l","c"}, ...]}

    Candlestick requires the chartjs-chart-financial plugin (loaded via CDN in
    the chart template when chart_type="candlestick").
    """
    color = config.get("color", config.get("accent", "#0d9488"))

    # [v1.2.8] Candlestick — rendered as native Chart.js 4 floating bar chart.
    # The chartjs-chart-financial plugin doesn't work with Chart.js 4 (unmaintained).
    # Instead: each bar = [low, high] (floating bar), colored green if close >= open,
    # red if close < open. OHLC values shown in tooltip. 100% native, no plugin.
    if isinstance(data, dict) and data.get("_candlestick"):
        ohlc = data.get("ohlc_data") or []
        # Build floating bar data: each point = [low, high]
        bar_data = []
        labels = []
        bar_colors = []
        for point in ohlc:
            o = point.get("o")
            h = point.get("h")
            l = point.get("l")
            c = point.get("c")
            t = point.get("t", "")
            if None in (o, h, l, c):
                continue
            labels.append(t)
            bar_data.append([l, h])  # floating bar from low to high
            # Green if close >= open (up day), red if close < open (down day)
            bar_colors.append("#22c55e" if c >= o else "#ef4444")

        # Store OHLC for tooltip
        ohlc_tooltips = []
        for point in ohlc:
            if None in (point.get("o"), point.get("h"), point.get("l"), point.get("c")):
                continue
            ohlc_tooltips.append(
                f"O: {point['o']:.2f}  H: {point['h']:.2f}  L: {point['l']:.2f}  C: {point['c']:.2f}"
            )

        return {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": title or "Price",
                    "data": bar_data,
                    "backgroundColor": bar_colors,
                    "borderColor": bar_colors,
                    "borderWidth": 1,
                    "barPercentage": 0.8,
                    "categoryPercentage": 0.9,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "x": {
                        "type": "category",
                    },
                    "y": {
                        "beginAtZero": False,
                    },
                },
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": bool(title), "text": title},
                    "tooltip": {
                        "callbacks": {
                            "label": None,  # set via _tooltip_labels below
                        },
                    },
                },
            },
            # Custom property — template reads this to override tooltip labels
            "_tooltip_labels": ohlc_tooltips,
        }

    if isinstance(data, dict):
        labels = data.get("x", data.get("labels", []))
        # Multi-series: datasets key present
        if "datasets" in data and isinstance(data["datasets"], list):
            palette = _generate_palette(len(data["datasets"]), color)
            datasets = []
            has_dual_axis = False
            for i, ds in enumerate(data["datasets"]):
                c = palette[i] if i < len(palette) else color
                entry = {
                    "label": ds.get("label", f"Series {i+1}"),
                    "data": ds.get("data", ds.get("y", [])),
                    "backgroundColor": c + "40",
                    "borderColor": c,
                    "borderWidth": 2,
                    "tension": 0.3,
                }
                # [v1.2.9] Dual-axis support: if a dataset has yAxisID, pass it through.
                # Adapters use this to put per-share values + ratios on separate axes
                # (e.g., DPA ~4.5 vs Div Yield ~0.10 would be unreadable on one axis).
                if ds.get("yAxisID"):
                    entry["yAxisID"] = ds["yAxisID"]
                    has_dual_axis = True
                datasets.append(entry)

            options: dict[str, Any] = {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": bool(title), "text": title},
                },
            }
            # [v1.2.9] Add dual-axis scales config when any dataset has yAxisID="y1"
            if has_dual_axis:
                options["scales"] = {
                    "x": {"grid": {"display": False}},
                    "y": {
                        "type": "linear",
                        "position": "left",
                        "grid": {"color": "rgba(128,128,128,0.1)"},
                    },
                    "y1": {
                        "type": "linear",
                        "position": "right",
                        "grid": {"drawOnChartArea": False},
                    },
                }

            return {
                "type": chart_type,
                "data": {"labels": labels, "datasets": datasets},
                "options": options,
            }
        # Single-series (backward-compatible)
        values = data.get("y", data.get("values", []))
    elif isinstance(data, list):
        values = data
        labels = list(range(len(data)))
    else:
        labels, values = [], []

    datasets = [{
        "label": title,
        "data": values,
        "backgroundColor": color + "40",
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
    """Generate n distinct colors."""
    palette = [
        "#0d9488", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
        "#14b8a6", "#6366f1", "#f97316", "#ec4899", "#84cc16",
    ]
    return [palette[i % len(palette)] for i in range(n)]
