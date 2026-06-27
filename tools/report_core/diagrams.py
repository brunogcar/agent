"""report_core/diagrams.py - Mermaid.js diagram builders.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from tools.report_core.paths import report_out_dir


def _sanitize_mermaid(src: str) -> str:
    """Sanitize a Mermaid syntax string for safe HTML rendering.

    Mermaid syntax uses characters like >, |, [, ] which must NOT be
    HTML-escaped. But we must strip actual HTML tags and event handlers
    that could execute JavaScript in the browser context.

    Strategy:
    1. Strip <script>, <iframe>, <object>, <embed> tags entirely
    2. Strip on* event handlers (onerror, onclick, etc.)
    3. Strip javascript: URLs
    4. Preserve all Mermaid syntax characters
    """
    # Remove dangerous HTML tags entirely
    src = re.sub(r"<script[^>]*>.*?</script>", "", src, flags=re.IGNORECASE | re.DOTALL)
    src = re.sub(r"<iframe[^>]*>.*?</iframe>", "", src, flags=re.IGNORECASE | re.DOTALL)
    src = re.sub(r"<object[^>]*>.*?</object>", "", src, flags=re.IGNORECASE | re.DOTALL)
    src = re.sub(r"<embed[^>]*>", "", src, flags=re.IGNORECASE)
    # Remove event handlers: onerror=, onclick=, etc.
    src = re.sub(r"\son\w+\s*=\s*[^\s>\"']+", "", src, flags=re.IGNORECASE)
    src = re.sub(r"\son\w+\s*=\s*\"[^\"]*\"", "", src, flags=re.IGNORECASE)
    src = re.sub(r"\son\w+\s*=\s*'[^']*'", "", src, flags=re.IGNORECASE)
    # Remove javascript: URLs
    src = re.sub(r"javascript:", "", src, flags=re.IGNORECASE)
    return src


def build(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a Mermaid diagram report and return HTML path."""
    diagram_type = config.get("diagram_type", "flowchart").lower()

    # data can be raw mermaid syntax string, or a dict with nodes/edges
    if isinstance(data, str):
        mermaid_src = _sanitize_mermaid(data)
    elif isinstance(data, dict):
        mermaid_src = _dict_to_mermaid(data, diagram_type)
    else:
        mermaid_src = "flowchart TD\n A[Start] --> B[End]"

    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "diagram"))
    html_path = out_dir / f"{safe_title}.html"

    from tools.report_core import html
    ctx = {
        "title": title,
        "mermaid_src": mermaid_src,
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
    }
    html.render_template("diagram.html", ctx, html_path)

    return {
        "type": "diagram",
        "title": title,
        "html_path": str(html_path),
        "diagram_type": diagram_type,
    }


def _dict_to_mermaid(data: dict, diagram_type: str) -> str:
    """Convert a simple dict representation to Mermaid syntax.

    HTML-escapes node labels to prevent XSS while preserving Mermaid syntax.
    """
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    lines = [f"{diagram_type} TD"]
    for n in nodes:
        nid = html.escape(str(n.get("id", "A")))
        label = html.escape(str(n.get("label", nid)))
        lines.append(f" {nid}[{label}]")
    for e in edges:
        src = html.escape(str(e.get("from", "A")))
        dst = html.escape(str(e.get("to", "B")))
        label = html.escape(str(e.get("label", "")))
        if label:
            lines.append(f" {src} -->|{label}| {dst}")
        else:
            lines.append(f" {src} --> {dst}")
    return "\n".join(lines)
