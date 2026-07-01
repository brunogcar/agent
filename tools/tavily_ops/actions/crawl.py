"""tools/tavily_ops/actions/crawl.py — Tavily crawl action handler.

v1.2 FIX: Pass coroutine factory instead of coroutine object.
"""
from __future__ import annotations

import tools.tavily_ops.client as _client
from core.contracts import fail, ok
from core.tracer import tracer
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.errors import _assert_safe_urls, _handle_tavily_error
from tools.tavily_ops import bridge

@register_action(
    "tavily",
    "crawl",
    help_text="""crawl — Recursively crawl a website and extract content from linked pages.
Required: url
Optional: query (contextual instructions), max_depth, max_breadth, limit, extract_depth, format""",
    examples=[
        'tavily(action="crawl", url="https://example.com")',
        'tavily(action="crawl", url="https://docs.python.org", query="focus on asyncio")',
    ],
)
def _action_crawl(
    url: str = "",
    query: str = "",
    max_depth: int = 3,
    max_breadth: int = 10,
    limit: int = 50,
    extract_depth: str = "basic",
    format: str = "markdown",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Crawl a website and return extracted content from linked pages."""
    if not url:
        return fail("action='crawl' requires url=", trace_id=trace_id)

    instructions = query if query else None

    err = _assert_safe_urls([url])
    if err:
        return fail(err, trace_id=trace_id)

    client = _client._get_singleton_client()
    is_keyless = _client._is_keyless_mode()

    if is_keyless:
        return fail(
            "action='crawl' requires a Tavily API key. Set TAVILY_API_KEY in .env.",
            trace_id=trace_id,
        )

    def _call():
        return client.crawl(
            url=url,
            instructions=instructions,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            extract_depth=extract_depth,
            format=format,
        )

    try:
        # v1.2 FIX: Pass factory (_call) not coroutine (_call())
        result = bridge._run_async_with_resilience(_call, trace_id=trace_id)
    except Exception as e:
        return _handle_tavily_error(e, trace_id=trace_id)

    response = ok(
        {
            "results": result.get("results", []),
            "url": url,
            "query": query,
            "keyless": is_keyless,
        },
        trace_id=trace_id,
    )

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("tavily", response, trace_id)
