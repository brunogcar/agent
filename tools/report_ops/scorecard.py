"""report_ops/scorecard.py — RAG status dashboard builder.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.report_ops.html import render_template, _write_manifest, _write_metrics
from tools.report_ops.paths import report_out_dir


def _rag_status(score: float, target: float) -> str:
    if target == 0:
        return "green" if score == 0 else "red"
    if score >= target:
        return "green"
    if score >= target * 0.8:
        return "amber"
    return "red"


def _rag_color(status: str, theme: str = "dark") -> str:
    colors = {
        "green": "#22c55e" if theme == "dark" else "#16a34a",
        "amber": "#f59e0b" if theme == "dark" else "#d97706",
        "red": "#ef4444" if theme == "dark" else "#dc2626",
    }
    return colors.get(status, "#94a3b8")


def _build_radar_config(dimensions: list[dict]) -> dict:
    labels = [d["name"] for d in dimensions]
    current_scores = [d.get("score", 0) for d in dimensions]
    target_scores = [d.get("target", 0) for d in dimensions]

    return {
        "type": "radar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Current",
                    "data": current_scores,
                    "fill": True,
                    "backgroundColor": "rgba(13, 148, 136, 0.2)",
                    "borderColor": "#0d9488",
                    "pointBackgroundColor": "#0d9488",
                    "pointBorderColor": "#fff",
                },
                {
                    "label": "Target",
                    "data": target_scores,
                    "fill": True,
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "borderColor": "#3b82f6",
                    "pointBackgroundColor": "#3b82f6",
                    "borderDash": [5, 5],
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "r": {
                    "angleLines": {"color": "rgba(148, 163, 184, 0.2)"},
                    "grid": {"color": "rgba(148, 163, 184, 0.2)"},
                    "pointLabels": {"color": "#94a3b8", "font": {"size": 11}},
                    "ticks": {"color": "#94a3b8", "backdropColor": "transparent"},
                    "suggestedMin": 0,
                    "suggestedMax": 100,
                }
            },
            "plugins": {
                "legend": {"position": "bottom", "labels": {"color": "#94a3b8", "font": {"size": 12}}}
            },
        },
    }


def build(trace_id: str, title: str, data: Any, config: dict) -> dict:
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "scorecard"))
    html_path = out_dir / f"{safe_title}.html"

    dimensions = data if isinstance(data, list) else []
    if not dimensions:
        raise ValueError("scorecard requires data=[{name, score, target}, ...]")

    theme = config.get("theme", "dark")
    accent = config.get("accent", "#0d9488")

    processed = []
    total_weight = 0.0
    weighted_score = 0.0
    for d in dimensions:
        score = float(d.get("score", 0))
        target = float(d.get("target", 0))
        weight = float(d.get("weight", 1.0))
        status = _rag_status(score, target)
        color = _rag_color(status, theme)
        processed.append({
            "name": d.get("name", "Untitled"),
            "score": score,
            "target": target,
            "weight": weight,
            "status": status,
            "color": color,
            "delta": score - target,
        })
        total_weight += weight
        weighted_score += score * weight

    overall = weighted_score / total_weight if total_weight > 0 else 0
    overall_status = _rag_status(overall, 100)

    radar_config = _build_radar_config(processed)

    ctx = {
        "title": title,
        "subtitle": config.get("subtitle", ""),
        "dimensions": processed,
        "overall_score": round(overall, 1),
        "overall_status": overall_status,
        "overall_color": _rag_color(overall_status, theme),
        # Escape </script> to prevent injection when JSON is embedded in <script> tags
        # v1.4 FIX: Use raw string to avoid invalid escape sequence \/.
        "radar_config_json": json.dumps(radar_config).replace("</", r"<\/"),
        "theme": theme,
        "accent": accent,
        "trace_id": trace_id,
    }
    render_template("scorecard.html", ctx, html_path)
    _write_manifest(trace_id, action="scorecard", title=title, files=[html_path.name], config=config)
    _write_metrics(trace_id, action="scorecard", title=title, files=[html_path.name], config=config)

    return {
        "type": "scorecard",
        "title": title,
        "html_path": str(html_path),
        "dimensions": len(processed),
        "overall_score": round(overall, 1),
    }
