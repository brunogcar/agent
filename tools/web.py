"""tools/web.py — Web search and scraping tool (thin @tool facade).

Routes all web actions to handlers in web_ops/actions/ via the DISPATCH dict.
This is the only file scanned by registry.py for @tool decorators;
web_ops/ submodules are invisible to the registry.

PARALLEL_SAFE = True because httpx.Client is thread-safe.
"""
from __future__ import annotations

from typing import Optional

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import web_ops to trigger DISPATCH auto-discovery before @meta_tool reads it.
# This must happen before the facade is defined.
from tools import web_ops  # noqa: F401
from tools.web_ops._registry import DISPATCH

# Module-level flags
PARALLEL_SAFE = True


@tool
@meta_tool(
    DISPATCH.get("web", {}),
    doc_sections=[
        "WHEN TO USE THIS TOOL:",
        " | Need | Tool | Why |",
        " |------|------|-----|",
        " | Quick search | web(search) | Free, SearXNG, no API costs |",
        " | Static page text (full) | web(scrape) | Fast, lightweight, no overhead |",
        " | Static page text (pruned) | web(read) | Same as scrape but with truncation guard |",
        " | Bulk scrape from search | web(search_and_read) | Parallel, automated, deduplicated |",
        " | JS-rendered page | browser(navigate+text_content) | Renders JavaScript |",
        "",
        "PARALLEL_SAFE = True — safe for parallel() usage.",
    ],
)
def web(
    action: str,
    query: str = "",
    url: str = "",
    max_results: int = 5,
    max_chars: Optional[int] = None,  # None = use cfg.web_max_text_chars (resolved in handlers)
    trace_id: str = "",
) -> dict:
    """Web meta-tool — atomic actions for search and scraping."""
    action = action.strip().lower()

    tracer.step(trace_id, "web", f"action={action}")

    op_info = DISPATCH.get("web", {}).get(action)
    if op_info is None:
        valid_actions = " | ".join(sorted(DISPATCH.get("web", {}).keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    handler = op_info["func"]

    # Build kwargs from facade params. Only pass max_chars when explicitly
    # provided; handlers resolve cfg.web_max_text_chars when max_chars is None.
    kwargs = {
        "query": query,
        "url": url,
        "max_results": max_results,
        "trace_id": trace_id,
    }
    if max_chars is not None:
        kwargs["max_chars"] = max_chars

    try:
        result = handler(**kwargs)
    except Exception as e:
        tracer.step(trace_id, "web", f"action={action}:failed")
        return fail(f"Web action failed: {e}", trace_id=trace_id)

    if result.get("status") == "error":
        tracer.step(trace_id, "web", f"action={action}:failed")
    else:
        tracer.step(trace_id, "web", f"action={action}:complete")

    return result
