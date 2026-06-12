"""
report_core/timeline.py — SVG Gantt/timeline builder.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from tools.report_core.html import render_template, _write_manifest, _write_metrics
from tools.report_core.paths import report_out_dir

STATUS_COLORS = {
    "done": "#22c55e",
    "active": "#3b82f6",
    "pending": "#94a3b8",
    "blocked": "#ef4444",
}


def _parse_date(d: str) -> datetime.date:
    return datetime.datetime.strptime(d, "%Y-%m-%d").date()


def _escape_svg(text: str) -> str:
    """Escape &, <, > for safe SVG text insertion."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_svg(events: list[dict], width: int = 900, bar_height: int = 32, row_gap: int = 48) -> str:
    if not events:
        return '<p style="color:var(--text-sec)">No timeline events.</p>'

    parsed = []
    for ev in events:
        try:
            start = _parse_date(ev["start"])
            end = _parse_date(ev["end"])
            parsed.append({
                "label": ev.get("label", "Untitled"),
                "start": start,
                "end": end,
                "status": ev.get("status", "pending"),
                "color": ev.get("color", STATUS_COLORS.get(ev.get("status", "pending"), "#94a3b8")),
            })
        except Exception:
            continue

    if not parsed:
        return '<p style="color:var(--text-sec)">Invalid date format. Use YYYY-MM-DD.</p>'

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
        f'<svg viewBox="0 0 {width} {chart_height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{width}px;">',
        f'  <rect width="{width}" height="{chart_height}" fill="none"/>',
    ]

    for tick in ticks:
        svg_parts.append(
            f'  <line x1="{tick["x"]:.1f}" y1="{margin_top}" x2="{tick["x"]:.1f}" y2="{chart_height - margin_bottom}"'
            f' stroke="var(--border)" stroke-width="0.5" stroke-dasharray="4,4"/>'
        )
        svg_parts.append(
            f'  <text x="{tick["x"]:.1f}" y="{margin_top - 10}" text-anchor="middle"'
            f' fill="var(--text-sec)" font-size="10" font-family="ui-monospace, monospace">{tick["label"]}</text>'
        )

    for i, ev in enumerate(parsed):
        y = margin_top + i * row_gap
        days_start = (ev["start"] - min_date).days
        days_end = (ev["end"] - min_date).days
        x = margin_left + (days_start / total_days) * chart_width
        w = max(2, ((days_end - days_start) / total_days) * chart_width)
        label = _escape_svg(ev["label"])

        svg_parts.append(
            f'  <text x="{margin_left - 10}" y="{y + bar_height / 2 + 4}" text-anchor="end"'
            f' fill="var(--text)" font-size="11" font-family="Inter, system-ui, sans-serif">{label}</text>'
        )

        if days_end == days_start:
            # Single-day milestone: diamond marker
            diamond_size = 8
            cx = x
            cy = y + bar_height / 2
            pts = f"{cx:.1f},{cy - diamond_size:.1f} {cx + diamond_size:.1f},{cy:.1f} {cx:.1f},{cy + diamond_size:.1f} {cx - diamond_size:.1f},{cy:.1f}"
            svg_parts.append(
                f'  <polygon points="{pts}" fill="{ev["color"]}" opacity="0.85"/>'
            )
        else:
            svg_parts.append(
                f'  <rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_height}"'
                f' rx="4" fill="{ev["color"]}" opacity="0.85"/>'
            )

        svg_parts.append(
            f'  <text x="{x + 6:.1f}" y="{y + bar_height / 2 + 4}"'
            f' fill="white" font-size="9" font-family="ui-monospace, monospace">'
            f'{ev["start"].strftime("%d/%m")} – {ev["end"].strftime("%d/%m")}</text>'
        )

    today = datetime.date.today()
    if min_date <= today <= max_date:
        tx = margin_left + ((today - min_date).days / total_days) * chart_width
        svg_parts.append(
            f'  <line x1="{tx:.1f}" y1="{margin_top}" x2="{tx:.1f}" y2="{chart_height - margin_bottom}"'
            f' stroke="#ef4444" stroke-width="1.5" stroke-dasharray="6,3"/>'
        )
        svg_parts.append(
            f'  <text x="{tx:.1f}" y="{margin_top - 22}" text-anchor="middle"'
            f' fill="#ef4444" font-size="9" font-weight="bold" font-family="ui-monospace, monospace">TODAY</text>'
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
