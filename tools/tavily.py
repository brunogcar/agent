"""tools/tavily.py — Tavily AI search & extraction tool (thin @tool facade).

Routes all tavily actions to handlers in tavily_ops/actions/ via the DISPATCH dict.
This is the only file scanned by registry.py for @tool decorators;
tavily_ops/ submodules are invisible to the registry.

PARALLEL_SAFE = True because AsyncTavilyClient is thread-safe.
"""
from __future__ import annotations

from typing import List, Optional

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import tavily_ops to trigger DISPATCH auto-discovery before @meta_tool reads it.
# This must happen before the facade is defined.
from tools import tavily_ops  # noqa: F401
from tools.tavily_ops._registry import DISPATCH

# Module-level flags
PARALLEL_SAFE = True


@tool
@meta_tool(
    DISPATCH.get("tavily", {}),
    doc_sections=[
        "WHEN TO USE THIS TOOL:",
        " | Need | Tool | Why |",
        " |------|------|-----|",
        " | AI-powered search with citations | tavily(search) | High-quality results, source links |",
        " | Extract content from URLs | tavily(extract) | Clean, structured extraction |",
        " | Crawl a website | tavily(crawl) | Recursive page extraction |",
        " | Map site structure | tavily(map) | URL discovery |",
        "",
        "PARALLEL_SAFE = True — safe for parallel() usage.",
    ],
)
def tavily(
    action: str,
    query: str = "",
    url: str = "",
    # v1.1: urls is a facade param for the extract action.
    # Must be in the signature so tavily(action="extract", urls=[...]) works.
    urls: Optional[List[str]] = None,
    max_results: int = 5,
    search_depth: str = "basic",
    include_answer: bool = True,
    include_raw_content: bool = False,
    include_images: bool = False,
    extract_depth: str = "basic",
    format: str = "markdown",
    citation_format: str = "numbered",
    topic: str = "general",
    time_range: str = "",
    # v1.1: Domain filtering for research scoping
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    max_chars: Optional[int] = None,
    trace_id: str = "",
) -> dict:
    """Tavily meta-tool — atomic actions for AI search, extraction, and crawling."""
    action = action.strip().lower()

    tracer.step(trace_id, "tavily", f"action={action}")

    op_info = DISPATCH.get("tavily", {}).get(action)
    if op_info is None:
        valid_actions = " | ".join(sorted(DISPATCH.get("tavily", {}).keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    handler = op_info["func"]

    kwargs = {
        "query": query,
        "url": url,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "include_images": include_images,
        "extract_depth": extract_depth,
        "format": format,
        "citation_format": citation_format,
        "topic": topic,
        "time_range": time_range,
        # v1.1: Pass domain filtering through to action handlers
        "include_domains": include_domains,
        "exclude_domains": exclude_domains,
        "trace_id": trace_id,
    }
    # v1.1: Only pass urls when explicitly provided (extract action)
    if urls is not None:
        kwargs["urls"] = urls
    if max_chars is not None:
        kwargs["max_chars"] = max_chars

    try:
        result = handler(**kwargs)
    except Exception as e:
        tracer.step(trace_id, "tavily", f"action={action}:failed")
        return fail(f"Tavily action failed: {e}", trace_id=trace_id)

    if not isinstance(result, dict):
        return fail(
            f"Handler returned {type(result).__name__}, expected dict.",
            trace_id=trace_id,
        )

    if result.get("status") == "error":
        tracer.step(trace_id, "tavily", f"action={action}:failed")
    else:
        tracer.step(trace_id, "tavily", f"action={action}:complete")

    return result
