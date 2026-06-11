"""
report_core/html.py - Jinja2 renderer.

Thread-safe: instantiates a new Environment per render call.
Templates live in report_core/templates/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.config import cfg


def _get_template_dir() -> Path:
    """Return the package templates directory."""
    return Path(__file__).with_suffix("").parent / "templates"


def render_template(template_name: str, context: dict, output_path: Path) -> None:
    """Render a Jinja2 template to an HTML file."""
    from jinja2 import Environment, FileSystemLoader  # lazy

    template_dir = _get_template_dir()
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(template_name)
    rendered = template.render(**context)
    output_path.write_text(rendered, encoding="utf-8")


def build_report(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a single-scroll HTML report."""
    data_path = config.get("data_path", "")
    from tools.report_core.data import load_data
    loaded, err = load_data(data=data, data_path=data_path)
    if err:
        raise ValueError(err)

    from tools.report_core.paths import report_out_dir
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "report"))
    html_path = out_dir / f"{safe_title}.html"

    sections = config.get("sections", [])
    kpis = config.get("kpis", [])
    sources = config.get("sources", [])

    ctx = {
        "title": title,
        "sections": sections,
        "kpis": kpis,
        "sources": sources,
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
        "data": loaded,
        "trace_id": trace_id,
    }
    render_template("report.html", ctx, html_path)

    return {
        "type": "report",
        "title": title,
        "html_path": str(html_path),
        "sections": len(sections),
    }


def build_dashboard(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a multi-panel dashboard."""
    data_path = config.get("data_path", "")
    from tools.report_core.data import load_data
    loaded, err = load_data(data=data, data_path=data_path)
    if err:
        raise ValueError(err)

    from tools.report_core.paths import report_out_dir
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "dashboard"))
    html_path = out_dir / f"{safe_title}.html"

    tabs = config.get("tabs", [])
    kpis = config.get("kpis", [])
    charts = config.get("charts", [])
    columns = max(1, min(config.get("columns", 2), 4))

    ctx = {
        "title": title,
        "subtitle": config.get("subtitle", ""),
        "tabs": tabs,
        "kpis": kpis,
        "charts": charts,
        "columns": columns,
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
        "data": loaded,
        "trace_id": trace_id,
    }
    render_template("dashboard.html", ctx, html_path)

    return {
        "type": "dashboard",
        "title": title,
        "html_path": str(html_path),
        "tabs": len(tabs),
        "charts": len(charts),
    }
