"""report_ops/table.py — Tabular statement builder.

Renders one or more tables (e.g. financial statements, ratio tables, shareholder
lists) as a single self-contained HTML report with sticky headers, per-column
number formatting, and a client-side search filter per table.

DATA SHAPE
----------
    data = {
        "sections": [
            {
                "title":   "Quarterly Summary",     # section heading
                "columns": ["Período", "Receita", ...],  # optional (derived from rows if omitted)
                "rows":    [ ["1T26", 1000, ...], ... ]  # list-of-lists
                          # OR list-of-dicts (columns derived from keys)
                "formats": {"Receita": "brl", ...},      # optional: spec per column NAME
                "note":    "optional caption",           # optional
            },
            ...
        ],
        "kpis":    [{"label","value","delta?","format?"}],  # optional top KPI strip
        "sources": [{"title","url","snippet?"}],            # optional source list
    }

ADAPTERS
--------
If ``config["adapter"]`` is set, the raw ``data`` is treated as a skill result
and flattened by the matching transform in ``tools/report_ops/transforms/``
before rendering. This lets the LLM pipe a skill JSON straight into the table
action:

    report(action="table", title="PETR4 Financials",
           data=<financials skill JSON>,
           config={"adapter": "financials_quarterly"})

Without an adapter, ``data`` must already be in the table shape above.

NUMBER FORMATTING
-----------------
Per-column specs ("brl","pct","num","int","compact","brl_full","pct_raw","text")
are honoured by the ``fmt`` Jinja filter (see formats.py) in HTML and by
``excel_format()`` in xlsx export — one spec tag, two consistent renderings.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.report_ops.html import render_template, _write_manifest, _write_metrics
from tools.report_ops.paths import report_out_dir


def _safe_title(title: str, default: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or default))


def _normalize_section(sec: dict, index: int) -> dict:
    """Normalize a section to {title, columns, rows, col_formats, note}.

    Accepts rows as list-of-lists or list-of-dicts. Derives columns when not
    provided. Builds col_formats (list aligned to columns) from a formats map
    keyed by column name.
    """
    title = sec.get("title") or f"Table {index + 1}"
    raw_rows = sec.get("rows") or []
    columns = list(sec.get("columns") or [])
    formats_map = sec.get("formats") or {}
    note = sec.get("note") or ""

    # Derive columns from first dict row if not provided
    if not columns and raw_rows and isinstance(raw_rows[0], dict):
        columns = list(raw_rows[0].keys())

    # Normalize rows to list-of-lists aligned to columns
    norm_rows: list[list] = []
    if columns:
        for r in raw_rows:
            if isinstance(r, dict):
                norm_rows.append([r.get(c) for c in columns])
            elif isinstance(r, (list, tuple)):
                # pad/trim to column count
                vals = list(r)
                if len(vals) < len(columns):
                    vals += [None] * (len(columns) - len(vals))
                norm_rows.append(vals[:len(columns)])
            else:
                norm_rows.append([r])
    else:
        # No columns: rows must be list-of-lists; synthesize Col 1..N
        for r in raw_rows:
            if isinstance(r, (list, tuple)):
                norm_rows.append(list(r))
            elif isinstance(r, dict):
                norm_rows.append(list(r.values()))
            else:
                norm_rows.append([r])
        if norm_rows:
            columns = [f"Col {i + 1}" for i in range(len(norm_rows[0]))]

    # Per-column format spec list aligned to columns
    col_formats = [formats_map.get(c, "text") for c in columns]

    return {
        "title": title,
        "columns": columns,
        "rows": norm_rows,
        "col_formats": col_formats,
        "note": note,
        "row_count": len(norm_rows),
    }


def _normalize_kpis(kpis: list) -> list:
    """Ensure each kpi has label/value/delta/format keys."""
    out = []
    for k in kpis or []:
        if not isinstance(k, dict):
            continue
        spec = k.get("format", "text")
        value = k.get("value", "")
        # Pre-format value if a spec is given and value is numeric-ish
        if spec and spec != "text":
            from tools.report_ops.formats import apply_fmt
            value = apply_fmt(value, spec)
        out.append({
            "label": k.get("label", ""),
            "value": value,
            "delta": k.get("delta", ""),
        })
    return out


def build(trace_id: str, title: str, data: Any, config: dict) -> dict:
    """Build a multi-table HTML report. See module docstring for data shape."""
    # Apply adapter if requested (flattens a raw skill result into table shape)
    adapter = (config.get("adapter") or "").strip()
    if adapter:
        from tools.report_ops.adapters import apply_adapter
        data = apply_adapter(adapter, data)

    if not isinstance(data, dict):
        raise ValueError(
            "table data must be a dict with 'sections' (or a skill result + "
            "config['adapter']). Got: " + type(data).__name__
        )

    raw_sections = data.get("sections") or []
    if not raw_sections:
        # Allow a bare list of sections or a single section dict
        if isinstance(data, list):
            raw_sections = data
        else:
            raise ValueError("table data has no 'sections' list")

    sections = [_normalize_section(s, i) for i, s in enumerate(raw_sections)]
    kpis = _normalize_kpis(data.get("kpis") or [])
    sources = data.get("sources") or []

    out_dir = report_out_dir(trace_id)
    safe = _safe_title(title, "table")
    html_path = out_dir / f"{safe}.html"

    # Embed sections JSON for the client-side search filter (</script>-escaped)
    # Only structural metadata is embedded — cell values are rendered server-side.
    filter_meta = json.dumps([{"idx": i, "rows": s["row_count"]} for i, s in enumerate(sections)]).replace("</", r"<\/")

    ctx = {
        "title": title,
        "subtitle": config.get("subtitle", ""),
        "company": data.get("company") or data.get("ticker") or "",
        "sections": sections,
        "kpis": kpis,
        "sources": sources,
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
        "trace_id": trace_id,
        "filter_meta_json": filter_meta,
    }
    render_template("table.html", ctx, html_path)

    _write_manifest(trace_id, action="table", title=title, files=[html_path.name], config=config)
    _write_metrics(trace_id, action="table", title=title, files=[html_path.name], config=config)

    return {
        "type": "table",
        "title": title,
        "html_path": str(html_path),
        "sections": len(sections),
        "total_rows": sum(s["row_count"] for s in sections),
        "adapter": adapter,
    }
