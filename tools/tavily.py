"""tools/tavily.py — Tavily AI search & extraction tool (thin @tool facade).

Routes all tavily actions to handlers in tavily_ops/actions/ via the DISPATCH dict.
This is the only file scanned by registry.py for @tool decorators;
tavily_ops/ submodules are invisible to the registry.

v1.2: Restored max_depth, max_breadth, limit facade params.
      Added error_code support in fail() responses.
v1.3: Added include_domains/exclude_domains validation.
      citation_format only passed to research action.

PARALLEL_SAFE = True because AsyncTavilyClient is thread-safe.
"""
from __future__ import annotations

from typing import List, Optional

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import tavily_ops to trigger DISPATCH auto-discovery before @meta_tool reads it.
from tools import tavily_ops  # noqa: F401
from tools.tavily_ops._registry import DISPATCH

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
    # v1.2: Restored facade params for crawl/map control
    max_depth: int = 3,
    max_breadth: int = 10,
    limit: int = 50,
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
            error_code="INVALID_ACTION",
        )

    handler = op_info["func"]

    # v1.3: Validate include_domains/exclude_domains are lists
    for param_name, param_val in [("include_domains", include_domains), ("exclude_domains", exclude_domains)]:
        if param_val is not None and not isinstance(param_val, list):
            return fail(
                f"{param_name} must be a list of strings, got {type(param_val).__name__}",
                trace_id=trace_id,
                error_code="INVALID_PARAM",
            )
        if param_val is not None:
            for item in param_val:
                if not isinstance(item, str):
                    return fail(
                        f"{param_name} must contain only strings, found {type(item).__name__}",
                        trace_id=trace_id,
                        error_code="INVALID_PARAM",
                    )

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
        "topic": topic,
        "time_range": time_range,
        # v1.2: Pass through restored params
        "max_depth": max_depth,
        "max_breadth": max_breadth,
        "limit": limit,
        "include_domains": include_domains,
        "exclude_domains": exclude_domains,
        "trace_id": trace_id,
    }
    if urls is not None:
        kwargs["urls"] = urls
    if max_chars is not None:
        kwargs["max_chars"] = max_chars

    # v1.3: Only pass citation_format to research action
    if action == "research":
        kwargs["citation_format"] = citation_format

    try:
        result = handler(**kwargs)
    except Exception as e:
        tracer.step(trace_id, "tavily", f"action={action}:failed")
        return fail(f"Tavily action failed: {e}", trace_id=trace_id, error_code="INTERNAL_ERROR")

    if not isinstance(result, dict):
        return fail(
            f"Handler returned {type(result).__name__}, expected dict.",
            trace_id=trace_id,
            error_code="INTERNAL_ERROR",
        )

    if result.get("status") == "error":
        tracer.step(trace_id, "tavily", f"action={action}:failed")
    else:
        tracer.step(trace_id, "tavily", f"action={action}:complete")

    return result
