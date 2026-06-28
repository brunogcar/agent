"""Browser action: extract_tables."""
from __future__ import annotations

import json

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


# JS template for extracting structured table data.
# Uses json.dumps() for safe selector injection (see extract_links.py).
_TABLES_JS = """
(() => {
    const tables = Array.from(document.querySelectorAll(SELECTOR));
    return tables.map(table => {
        const rows = Array.from(table.querySelectorAll("tr"));
        const headers = rows.length > 0
            ? Array.from(rows[0].querySelectorAll("th,td")).map(c => c.textContent.trim())
            : [];
        const data = rows.slice(1).map(row =>
            Array.from(row.querySelectorAll("td,th")).map(c => c.textContent.trim())
        );
        return { headers, rows: data, row_count: data.length };
    });
})()
"""


@register_action(
    "browser",
    "extract_tables",
    help_text="""extract_tables — Extract all tables from the page or a specific element as structured data.
Required: none
Optional: selector, timeout, headless, trace_id""",
    examples=[
        'browser(action="extract_tables")',
        'browser(action="extract_tables", selector=".data-table")',
    ],
)
def _action_extract_tables(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Extract all tables from the page or a specific element as structured data.

    When selector is empty, defaults to "table" (all table elements).
    Uses json.dumps() for safe JS string injection.
    """
    try:
        with _browser_lock:
            page = _run_browser_async(
                _get_page(trace_id, headless), timeout=timeout + 5
            )
            # Default to "table" when selector is empty.
            effective_selector = selector or "table"
            js = _TABLES_JS.replace("SELECTOR", json.dumps(effective_selector))
            result = _run_browser_async(
                page.evaluate(js), timeout=timeout + 5
            )
            tables = result if isinstance(result, list) else []
            return ok({"tables": tables, "count": len(tables)}, trace_id=trace_id)
    except Exception as e:
        return fail(f"extract_tables failed: {e}", trace_id=trace_id)
