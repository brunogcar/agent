"""
report_core/html.py - Jinja2 renderer.

Thread-safe: uses a module-level singleton Environment with autoescape enabled.
Templates live in report_core/templates/.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from core.config import cfg

_JINJA_ENV = None


def _get_template_dir() -> Path:
    """Return the package templates directory."""
    return Path(__file__).resolve().parent / "templates"


def _get_env():
    """Lazy singleton Jinja2 Environment with autoescape."""
    global _JINJA_ENV
    if _JINJA_ENV is None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        _JINJA_ENV = Environment(
            loader=FileSystemLoader(str(_get_template_dir())),
            autoescape=select_autoescape(["html", "xml"]),
        )
    return _JINJA_ENV


def render_template(template_name: str, context: dict, output_path: Path) -> None:
    """Render a Jinja2 template to an HTML file."""
    env = _get_env()
    template = env.get_template(template_name)
    rendered = template.render(**context)
    output_path.write_text(rendered, encoding="utf-8")


def _atomic_write(path: Path, content: str) -> None:
    """Atomic file write via temp + os.replace."""
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _write_manifest(
    trace_id: str,
    action: str,
    title: str,
    files: list,
    config: dict,
) -> None:
    """Write manifest.json alongside the HTML report."""
    from tools.report_core.paths import report_out_dir
    out_dir = report_out_dir(trace_id)
    manifest = {
        "trace_id": trace_id,
        "action": action,
        "title": title,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files": files,
        "preset": config.get("preset", ""),
        "theme": config.get("theme", "dark"),
    }
    manifest_path = out_dir / "manifest.json"
    _atomic_write(manifest_path, json.dumps(manifest, indent=2))


def _write_metrics(
    trace_id: str,
    action: str,
    title: str,
    files: list,
    config: dict,
) -> None:
    """Write metrics.json for Grafana/external ingestion."""
    from tools.report_core.paths import report_out_dir
    out_dir = report_out_dir(trace_id)
    metrics = {
        "trace_id": trace_id,
        "action": action,
        "title": title,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files_count": len(files),
        "preset": config.get("preset", ""),
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", ""),
        "chart_engine": config.get("chart_engine", ""),
        "has_data": bool(config.get("data_path") or config.get("sections") or config.get("tabs")),
    }
    metrics_path = out_dir / "metrics.json"
    _atomic_write(metrics_path, json.dumps(metrics, indent=2))


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

    _write_manifest(trace_id, action="report", title=title, files=[html_path.name], config=config)
    _write_metrics(trace_id, action="report", title=title, files=[html_path.name], config=config)

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

    _write_manifest(trace_id, action="dashboard", title=title, files=[html_path.name], config=config)
    _write_metrics(trace_id, action="dashboard", title=title, files=[html_path.name], config=config)

    return {
        "type": "dashboard",
        "title": title,
        "html_path": str(html_path),
        "tabs": len(tabs),
        "charts": len(charts),
    }
