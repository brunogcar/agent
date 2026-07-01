"""tools/tavily_ops/actions/search.py — Tavily search action handler.

v1.2 FIXES:
- Pass coroutine factory (_call) not coroutine object (_call()) to resilience.
- Restore raw_content stripping when include_raw_content=False.
- Use core/net/errors for retry classification.
"""
from __future__ import annotations

from typing import List, Optional

import tools.tavily_ops.client as _client
from core.contracts import fail, ok
from core.tracer import tracer
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.errors import _handle_tavily_error
from tools.tavily_ops import bridge

@register_action(
    "tavily",
    "search",
    help_text="""search — AI-powered web search with source citations.
Required: query
Optional: max_results (default 5), search_depth (basic|advanced), include_answer, include_raw_content, include_images, include_domains, exclude_domains, topic, time_range""",
    examples=[
        'tavily(action="search", query="FastMCP python tutorial")',
        'tavily(action="search", query="ChromaDB persistent client", max_results=10)',
    ],
)
def _action_search(
    query: str = "",
    max_results: int = 5,
    search_depth: str = "basic",
    include_answer: bool = True,
    include_raw_content: bool = False,
    include_images: bool = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    topic: str = "general",
    time_range: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Call Tavily search and return structured results with citations.

    v1.2 CHANGES:
    - Fixed coroutine factory pattern for retry compatibility.
    - Restored raw_content stripping for token efficiency.
    """
    if not query:
        return fail("action='search' requires query=", trace_id=trace_id)

    if max_results < 1:
        return fail("max_results must be >= 1", trace_id=trace_id)
    if max_results > 20:
        return fail("max_results must be <= 20", trace_id=trace_id)

    client = _client._get_singleton_client()
    is_keyless = _client._is_keyless_mode()

    if is_keyless:
        _client._warn_keyless_once()

    if is_keyless and max_results > 3:
        max_results = 3

    def _call():
        return client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            include_images=include_images,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            topic=topic,
            time_range=time_range,
        )

    try:
        # v1.2 FIX: Pass factory (_call) not coroutine (_call())
        result = bridge._run_async_with_resilience(_call, trace_id=trace_id)
    except Exception as e:
        return _handle_tavily_error(e, trace_id=trace_id)

    # v1.2 FIX: Strip raw_content when not requested
    if not include_raw_content and "results" in result:
        for r in result.get("results", []):
            r.pop("raw_content", None)

    response = ok(
        {
            "results": result.get("results", []),
            "query": query,
            "count": len(result.get("results", [])),
            "answer": result.get("answer", ""),
            "keyless": is_keyless,
        },
        trace_id=trace_id,
    )

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("tavily", response, trace_id)
