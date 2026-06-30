"""tools/tavily_ops/actions/search.py — Tavily search action handler.

Calls AsyncTavilyClient.search() to perform AI-powered web search.
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
    # v1.1: Domain filtering for research scoping
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    topic: str = "general",
    time_range: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Call Tavily search and return structured results with citations.

    v1.1 CHANGES:
    - Added max_results validation (1-20) to prevent confusing SDK errors and OOM.
    - Passed include_images to SDK (was silently dropped before).
    - Added include_domains/exclude_domains for research scoping.
    """
    if not query:
        return fail("action='search' requires query=", trace_id=trace_id)

    # v1.1: Validate max_results range. Tavily API caps at 20; clamping here
    # prevents confusing SDK errors and protects against OOM from massive result sets.
    if max_results < 1:
        return fail("max_results must be >= 1", trace_id=trace_id)
    if max_results > 20:
        return fail("max_results must be <= 20", trace_id=trace_id)

    client = _client._get_singleton_client()
    is_keyless = _client._is_keyless_mode()

    # v1.1: Log one-time warning when running in keyless mode.
    if is_keyless:
        _client._warn_keyless_once()

    # Keyless mode: cap max_results to 3 to stay within free-tier limits
    if is_keyless and max_results > 3:
        max_results = 3

    def _call():
        return client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            # v1.1: Pass include_images to SDK (was silently dropped before)
            include_images=include_images,
            # v1.1: Surface domain filtering for research scoping
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            topic=topic,
            time_range=time_range,
        )

    try:
        # v1.1: Use _run_async_with_resilience for circuit breaker + retry
        result = bridge._run_async_with_resilience(_call(), trace_id=trace_id)
    except Exception as e:
        return _handle_tavily_error(e, trace_id=trace_id)

    # v1.1: Include answer and keyless flag in response for test compatibility
    # and LLM context awareness.
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
