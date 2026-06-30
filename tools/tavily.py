"""tools/tavily.py — Tavily AI research tool.
Thin @tool + @meta_tool facade for MCP compatibility.

Actions (exposed to LLM):
  search, extract, crawl, map

research action is implemented in tavily_ops/actions/research.py but NOT
exposed in the facade. Reserved for workflows/deep_research_impl/.
"""
from __future__ import annotations
from typing import Optional

from registry import tool
from tools._meta_tool import meta_tool
from tools.tavily_ops._registry import DISPATCH
from core.contracts import fail

# Import to trigger auto-discovery before @meta_tool reads DISPATCH
import tools.tavily_ops  # noqa: F401

PARALLEL_SAFE = True


@tool
@meta_tool(
    DISPATCH.get("tavily", {}),
    doc_sections=[
        "WHEN TO USE THIS TOOL:",
        " | Need | Tool | Why |",
        " |------|------|-----|",
        " | Quick search (free) | web(search) | SearXNG, no API costs |",
        " | AI-ranked search | tavily(search) | Better relevance, citations |",
        " | Single static page (free) | web(read) | Fast, no API costs |",
        " | Bulk URL extraction | tavily(extract) | Up to 10 URLs, AI-powered |",
        " | Site crawling | tavily(crawl) | Follows links (API key required) |",
        " | Site structure | tavily(map) | Hierarchy only (API key required) |",
        " | Deep research | workflows/deep_research.py | Not a tool action |",
        " | JS-rendered page | browser(navigate+text_content) | Renders JS |",
        "",
        "Requires TAVILY_API_KEY in .env for full functionality. Keyless",
        "mode supports search/extract with lower limits (max_results capped at 3).",
        "PARALLEL_SAFE = True — pure network I/O, no shared mutable state.",
    ],
)
def tavily(
    action: str,
    query: str = "",
    urls: Optional[list[str]] = None,
    url: str = "",
    max_results: int = 5,
    search_depth: str = "basic",
    topic: Optional[str] = None,
    time_range: Optional[str] = None,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    include_answer: bool = True,
    include_raw_content: bool = False,
    include_images: bool = False,
    extract_depth: str = "basic",
    format: str = "markdown",
    max_depth: int = 2,
    max_breadth: int = 10,
    limit: int = 100,
    trace_id: str = "",
) -> dict:
    """Tavily AI research tool — atomic actions for search/extract/crawl/map."""
    action = action.strip().lower()

    op_info = DISPATCH.get("tavily", {}).get(action)
    if op_info is None:
        valid = " | ".join(sorted(DISPATCH.get("tavily", {}).keys()))
        return fail(f"Unknown action '{action}'. Use: {valid}", trace_id=trace_id)

    kwargs = {
        "query": query,
        "urls": urls,
        "url": url,
        "max_results": max_results,
        "search_depth": search_depth,
        "topic": topic,
        "time_range": time_range,
        "include_domains": include_domains,
        "exclude_domains": exclude_domains,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "include_images": include_images,
        "extract_depth": extract_depth,
        "format": format,
        "max_depth": max_depth,
        "max_breadth": max_breadth,
        "limit": limit,
        "trace_id": trace_id,
    }

    try:
        result = op_info["func"](**kwargs)
    except Exception as e:
        return fail(f"Tavily action failed: {e}", trace_id=trace_id)

    if not isinstance(result, dict):
        return fail(
            f"Handler for '{action}' returned {type(result).__name__}, expected dict",
            trace_id=trace_id,
        )

    return result
