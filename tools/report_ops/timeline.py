"""report_ops/timeline.py — SVG Gantt/timeline builder.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

from tools.report_ops.html import render_template, _write_manifest, _write_metrics
from tools.report_ops.paths import report_out_dir

STATUS_COLORS = {
    "done": "#22c55e",
    "active": "#3b82f6",
    "pending": "#94a3b8",
    "blocked": "#ef4444",
}


def _parse_date(d: str) -> datetime.date:
    return datetime.datetime.strptime(d, "%Y-%m-%d").date()


def _escape_svg(text: str) -> str:
    """Escape &, <, >, " for safe SVG text insertion."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _validate_hex_color(color: str, fallback: str) -> str:
    """Validate a hex color string. Returns fallback if invalid."""
    if color and re.match(r"^#[0-9a-fA-F]{6}$", color):
        return color
    return fallback


def _build_svg(events: list[dict], width: int = 900, bar_height: int = 32, row_gap: int = 48) -> str:
    if not events:
        return '<div style="padding: 40px; text-align: center; color: var(--text-sec);">No timeline events.</div>'

    parsed = []
    for ev in events:
        try:
            start = _parse_date(ev["start"])
            end = _parse_date(ev["end"])
            status = ev.get("status", "pending")
            # Validate color — only accept valid hex, fallback to status color
            raw_color = ev.get("color", "")
            fallback_color = STATUS_COLORS.get(status, "#94a3b8")
            safe_color = _validate_hex_color(raw_color, fallback_color)
            parsed.append({
                "label": ev.get("label", "Untitled"),
                "start": start,
                "end": end,
                "status": status,
                "color": safe_color,
            })
        except Exception:
            continue

    if not parsed:
        return '<div style="padding: 40px; text-align: center; color: var(--text-sec);">Invalid date format. Use YYYY-MM-DD.</div>'

    min_date = min(e["start"] for e in parsed)
    max_date = max(e["end"] for e in parsed)
    total_days = max((max_date - min_date).days, 1)

    margin_left = 160
    margin_top = 40
    margin_right = 40
    margin_bottom = 40
    chart_width = width - margin_left - margin_right
    chart_height = margin_top + len(parsed) * row_gap + margin_bottom

    ticks = []
    current = datetime.date(min_date.year, min_date.month, 1)
    while current <= max_date:
        days_from_start = (current - min_date).days
        x = margin_left + (days_from_start / total_days) * chart_width
        ticks.append({"x": x, "label": current.strftime("%b %Y")})
        if current.month == 12:
            current = datetime.date(current.year + 1, 1, 1)
        else:
            current = datetime.date(current.year, current.month + 1, 1)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {chart_height}" style="width:100%;height:auto;">',
        f'<rect width="{width}" height="{chart_height}" fill="var(--bg-sec)" rx="12"/>',
    ]

    for tick in ticks:
        svg_parts.append(
            f'<line x1="{tick["x"]:.1f}" y1="{margin_top}" x2="{tick["x"]:.1f}" y2="{chart_height - margin_bottom}" stroke="var(--border)" stroke-width="1" stroke-dasharray="4,4"/>'
        )
        svg_parts.append(
            f'<text x="{tick["x"]:.1f}" y="{chart_height - margin_bottom + 20}" fill="var(--text-sec)" font-size="11" text-anchor="middle">{tick["label"]}</text>'
        )

    for i, ev in enumerate(parsed):
        y = margin_top + i * row_gap
        days_start = (ev["start"] - min_date).days
        days_end = (ev["end"] - min_date).days
        x = margin_left + (days_start / total_days) * chart_width
        w = max(2, ((days_end - days_start) / total_days) * chart_width)
        label = _escape_svg(ev["label"])

        svg_parts.append(
            f'<text x="{margin_left - 10}" y="{y + bar_height / 2 + 4}" fill="var(--text-sec)" font-size="12" text-anchor="end">{label}</text>'
        )

        if days_end == days_start:
            # Single-day milestone: diamond marker
            diamond_size = 8
            cx = x
            cy = y + bar_height / 2
            pts = f"{cx:.1f},{cy - diamond_size:.1f} {cx + diamond_size:.1f},{cy:.1f} {cx:.1f},{cy + diamond_size:.1f} {cx - diamond_size:.1f},{cy:.1f}"
            svg_parts.append(
                f'<polygon points="{pts}" fill="{ev["color"]}"/>'
            )
        else:
            svg_parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_height}" rx="6" fill="{ev["color"]}" opacity="0.85"/>'
            )

        svg_parts.append(
            f'<text x="{x + w / 2:.1f}" y="{y + bar_height / 2 + 4}" fill="white" font-size="10" text-anchor="middle">'
            f'{ev["start"].strftime("%d/%m")} – {ev["end"].strftime("%d/%m")}</text>'
        )

    today = datetime.date.today()
    if min_date <= today <= max_date:
        tx = margin_left + ((today - min_date).days / total_days) * chart_width
        svg_parts.append(
            f'<line x1="{tx:.1f}" y1="{margin_top}" x2="{tx:.1f}" y2="{chart_height - margin_bottom}" stroke="#ef4444" stroke-width="2" stroke-dasharray="6,3"/>'
        )
        svg_parts.append(
            f'<text x="{tx:.1f}" y="{margin_top - 8}" fill="#ef4444" font-size="10" font-weight="700" text-anchor="middle">TODAY</text>'
        )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def build(trace_id: str, title: str, data: Any, config: dict) -> dict:
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "timeline"))
    html_path = out_dir / f"{safe_title}.html"

    events = data if isinstance(data, list) else []
    if not events:
        raise ValueError("timeline requires data=[{label, start, end, status}, ...]")

    svg_html = _build_svg(
        events,
        width=config.get("width", 900),
        bar_height=config.get("bar_height", 32),
        row_gap=config.get("row_gap", 48),
    )

    ctx = {
        "title": title,
        "subtitle": config.get("subtitle", ""),
        "svg_html": svg_html,
        "events": events,
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
        "trace_id": trace_id,
    }
    render_template("timeline.html", ctx, html_path)
    _write_manifest(trace_id, action="timeline", title=title, files=[html_path.name], config=config)
    _write_metrics(trace_id, action="timeline", title=title, files=[html_path.name], config=config)

    return {
        "type": "timeline",
        "title": title,
        "html_path": str(html_path),
        "events": len(events),
    }
