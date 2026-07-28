"""report_ops/html.py - Jinja2 renderer.

Thread-safe: uses a module-level singleton Environment with autoescape enabled.
Templates live in report_ops/templates/.

All file writes are atomic (temp file + os.replace) to prevent partial writes
on crash or concurrent access.
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
    """Lazy singleton Jinja2 Environment with autoescape + number filters.

    Filters registered (see report_ops/formats.py):
      brl(value, suffix=True)      -> R$ 1,23 B / R$ 1.234,56
      pct(value, already_pct=False) -> 12,34%
      num(value, decimals=2)       -> 1.234,56
      int(value)                   -> 1.234
      compact(value)               -> 1,23 B
      dash(value)                  -> None -> "—"
      fmt(value, spec)             -> dispatch by spec tag ("brl","pct",...)
    """
    global _JINJA_ENV
    if _JINJA_ENV is None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        from tools.report_ops import formats
        _JINJA_ENV = Environment(
            loader=FileSystemLoader(str(_get_template_dir())),
            autoescape=select_autoescape(["html", "xml"]),
        )
        _JINJA_ENV.filters["brl"] = formats.fmt_brl
        _JINJA_ENV.filters["pct"] = formats.fmt_pct
        _JINJA_ENV.filters["num"] = formats.fmt_num
        _JINJA_ENV.filters["int"] = formats.fmt_int
        _JINJA_ENV.filters["compact"] = formats.fmt_compact
        _JINJA_ENV.filters["dash"] = formats.fmt_dash
        _JINJA_ENV.filters["fmt"] = formats.apply_fmt
    return _JINJA_ENV


def render_template(template_name: str, context: dict, output_path: Path) -> None:
    """Render a Jinja2 template to an HTML file (atomic write)."""
    env = _get_env()
    template = env.get_template(template_name)
    rendered = template.render(**context)
    _atomic_write(output_path, rendered)


def _atomic_write(path: Path, content: str) -> None:
    """Atomic file write via temp + os.replace.

    Prevents partial/corrupted files if the process crashes mid-write
    or if another reader accesses the file concurrently.
    """
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
    from tools.report_ops.paths import report_out_dir
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
    from tools.report_ops.paths import report_out_dir
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


def _normalize_table_sections(sections: list) -> None:
    """Normalize table sections in-place so the templates can render them.

    Three responsibilities (all fixed in v1.2):

    1. **List-of-dicts → columns + rows with PROPER alignment.**
       Previously used ``list(d.values())`` per row, which misaligns cells if
       any row after the first has a different key set or insertion order than
       row 0.  Now builds each row explicitly as ``[d.get(k) for k in columns]``
       so cells always line up with the header.

    2. **Empty data list → placeholder, not silent vanish.**
       Previously, an empty ``data`` list left the section with neither
       ``columns`` nor ``rows`` set, and the template guard
       ``{% if sec.columns and sec.rows %}`` silently dropped the entire
       section with no feedback.  Now sets ``columns=[]`` and ``rows=[]``
       explicitly so the template can render a "No data" placeholder.

    3. **Apply per-column format specs (``sec["formats"]``).**
       Previously, the ``formats`` dict was dead code on the report/dashboard
       path — only the standalone ``table`` action (table.py) honored it.
       Now applies ``apply_fmt(cell, spec)`` to each cell at normalization
       time, matching table.py's behavior.  This makes the backtest adapter's
       carefully-built format specs (brl_full, pct_raw, int) actually render
       as R$/%/thousands-formatted strings instead of raw floats.
    """
    from tools.report_ops.formats import apply_fmt

    for sec in sections or []:
        if not isinstance(sec, dict):
            continue
        if sec.get("type") != "table":
            continue

        # ── (1) + (2): Derive columns/rows from data list if not already set ──
        if not (sec.get("columns") and sec.get("rows")):
            data_list = sec.get("data")
            if isinstance(data_list, list) and data_list and isinstance(data_list[0], dict):
                sec["columns"] = list(data_list[0].keys())
                # Build each row ALIGNED to columns — NOT list(d.values()),
                # which would misalign if a row has different key order.
                sec["rows"] = [[d.get(k) for k in sec["columns"]] for d in data_list]
            elif isinstance(data_list, list) and not data_list:
                # Empty data list: set empty columns/rows so the template
                # renders a placeholder instead of silently skipping.
                sec.setdefault("columns", [])
                sec.setdefault("rows", [])

        # ── (3): Apply per-column format specs to pre-format cell values ──────
        # Only applies when a formats dict is present.  Sections without a
        # formats dict (e.g. pre-formatted performance summary) pass through
        # unchanged.  This makes sec["formats"] live on the report/dashboard
        # path — previously dead code (only table.py honored it).
        formats_map = sec.get("formats") or {}
        if formats_map and sec.get("columns") and sec.get("rows"):
            col_formats = [formats_map.get(c, "text") for c in sec["columns"]]
            sec["rows"] = [
                [apply_fmt(cell, col_formats[j]) for j, cell in enumerate(row)]
                for row in sec["rows"]
            ]
            # Clear formats so re-normalization is a no-op (idempotency).
            sec["formats"] = {}


def _apply_adapter_if_requested(config: dict, data: Any) -> Any:
    """Apply a report adapter if config['adapter'] is set; otherwise pass data through.

    Used by both build_report() and build_dashboard() so adapter support is
    identical across the two multi-section actions (table/chart already had it).
    """
    adapter = (config.get("adapter") or "").strip()
    if adapter:
        from tools.report_ops.adapters import apply_adapter
        data = apply_adapter(adapter, data)
    return data, adapter


def build_report(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a single-scroll HTML report.

    Accepts:
      - data={} (no failure — renders config-driven sections if any)
      - data=<skill JSON> + config['adapter'] (adapter flattens to sections/kpis)
      - data={"sections": [...], "kpis": [...]} (pre-shaped report payload)
      - data=<file path via config['data_path']> (loaded via path guard)
      - config['sections']/['kpis']/['sources'] (inline sections)
    """
    # Apply adapter if requested (flattens a raw skill result into report shape)
    data, adapter = _apply_adapter_if_requested(config, data)

    # If data is a dict with sections/kpis, use those (adapter output or pre-shaped)
    if isinstance(data, dict) and ("sections" in data or "kpis" in data):
        sections = data.get("sections", []) or []
        kpis = data.get("kpis", []) or []
        sources = data.get("sources", []) or []
        loaded: Any = data
    else:
        # Fall back to config-driven sections + optional data_path load
        data_path = config.get("data_path", "")
        if data_path:
            from tools.report_ops.data import load_data
            loaded, err = load_data(data=data, data_path=data_path)
            if err:
                raise ValueError(err)
        else:
            # No data_path: accept data={} or None without failing
            loaded = data
        sections = config.get("sections", []) or []
        kpis = config.get("kpis", []) or []
        sources = config.get("sources", []) or []

    # Normalize table sections (list-of-dicts → columns + rows)
    _normalize_table_sections(sections)

    from tools.report_ops.paths import report_out_dir
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "report"))
    html_path = out_dir / f"{safe_title}.html"

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
        "adapter": adapter,
    }


def build_dashboard(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a multi-panel dashboard.

    Accepts the same data shapes as build_report() and additionally normalizes
    table sections inside each tab.sections list.
    """
    # Apply adapter if requested (flattens a raw skill result into report shape)
    data, adapter = _apply_adapter_if_requested(config, data)

    # If data is a dict with sections/kpis/tabs, use those (adapter output or pre-shaped)
    if isinstance(data, dict) and ("sections" in data or "kpis" in data or "tabs" in data):
        tabs = data.get("tabs", []) or []
        kpis = data.get("kpis", []) or []
        charts = data.get("charts", []) or []
        sources = data.get("sources", []) or []
        loaded: Any = data
    else:
        data_path = config.get("data_path", "")
        if data_path:
            from tools.report_ops.data import load_data
            loaded, err = load_data(data=data, data_path=data_path)
            if err:
                raise ValueError(err)
        else:
            loaded = data
        tabs = config.get("tabs", []) or []
        kpis = config.get("kpis", []) or []
        charts = config.get("charts", []) or []
        sources = config.get("sources", []) or []

    # Normalize table sections inside every tab
    for tab in tabs:
        if isinstance(tab, dict):
            _normalize_table_sections(tab.get("sections", []))

    from tools.report_ops.paths import report_out_dir
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "dashboard"))
    html_path = out_dir / f"{safe_title}.html"

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
        "adapter": adapter,
    }
