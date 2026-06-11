"""
report_core/export.py - PDF/PNG export via Playwright (optional).

Playwright is imported lazily. If not installed, returns a graceful warning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.path_guard import resolve_path
from tools.report_core.paths import report_out_dir


def run(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """
    Export an existing HTML file to PDF or PNG.
    data: path to existing HTML file (relative to workspace or absolute)
    config["format"]: "pdf" | "png"
    """
    html_path_str = data if isinstance(data, str) else config.get("html_path", "")
    if not html_path_str:
        raise ValueError("data must be the path to an existing HTML file")

    p, err = resolve_path(html_path_str)
    if err:
        raise ValueError(err)
    if not p.exists():
        raise ValueError(f"HTML file not found: {p}")

    fmt = config.get("format", "pdf").lower()
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "export"))

    try:
        from playwright.sync_api import sync_playwright  # lazy
    except ImportError:
        return {
            "status": "success",
            "html_path": str(p),
            "pdf_path": None,
            "png_path": None,
            "warning": "playwright not installed - install with: pip install playwright",
        }

    export_path = out_dir / f"{safe_title}.{fmt}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///{p.resolve().as_posix()}")
        # Expand all tabs/collapsibles before export
        page.evaluate("""
            document.querySelectorAll('.tab-panel').forEach(el => el.classList.add('active'));
            document.querySelectorAll('.collapsible').forEach(el => el.classList.add('open'));
            document.querySelectorAll('.sidebar, .topbar, .btn-icon').forEach(el => el.style.display='none');
        """)
        if fmt == "pdf":
            page.pdf(path=str(export_path), format="A4", print_background=True)
        else:
            page.screenshot(path=str(export_path), full_page=True)
        browser.close()

    return {
        "status": "success",
        "html_path": str(p),
        f"{fmt}_path": str(export_path),
    }
