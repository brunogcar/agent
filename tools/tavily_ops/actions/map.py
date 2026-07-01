"""tools/tavily_ops/actions/map.py — Tavily map action handler.

v1.2 FIX: Pass coroutine factory instead of coroutine object.
v1.3 FIXES:
- Wire core/net/default constants.
- Wire budget tracking.
"""
from __future__ import annotations

import tools.tavily_ops.client as _client
from core.contracts import fail, ok
from core.net.budget import record_tool_call, check_budget
from core.net.default import CRAWL_MAX_DEPTH, CRAWL_MAX_BREADTH, CRAWL_LIMIT
from core.tracer import tracer
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.errors import _assert_safe_urls, _handle_tavily_error
from tools.tavily_ops import bridge

@register_action(
    "tavily",
    "map",
    help_text="""map — Discover and map URLs from a starting point.
Required: url
Optional: query (contextual instructions), max_depth, max_breadth, limit""",
    examples=[
        'tavily(action="map", url="https://example.com")',
        'tavily(action="map", url="https://docs.python.org", query="API reference pages")',
    ],
)
def _action_map(
    url: str = "",
    query: str = "",
    max_depth: int = CRAWL_MAX_DEPTH,
    max_breadth: int = CRAWL_MAX_BREADTH,
    limit: int = CRAWL_LIMIT,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Map a website and return discovered URLs.

    v1.3: Wired default constants and budget tracking.
    """
    if not url:
        return fail("action='map' requires url=", trace_id=trace_id)

    instructions = query if query else None

    err = _assert_safe_urls([url])
    if err:
        return fail(err, trace_id=trace_id)

    # v1.3: Budget check
    if not check_budget("tavily.map"):
        return fail(
            "Tavily map budget exhausted. Try again tomorrow.",
            trace_id=trace_id,
            error_code="QUOTA_EXHAUSTED",
        )

    client = _client._get_singleton_client()
    is_keyless = _client._is_keyless_mode()

    if is_keyless:
        return fail(
            "action='map' requires a Tavily API key. Set TAVILY_API_KEY in .env.",
            trace_id=trace_id,
        )

    def _call():
        return client.map(
            url=url,
            instructions=instructions,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
        )

    try:
        # v1.2 FIX: Pass factory (_call) not coroutine (_call())
        result = bridge._run_async_with_resilience(_call, trace_id=trace_id)
    except Exception as e:
        return _handle_tavily_error(e, trace_id=trace_id)

    # v1.3: Record successful API call
    record_tool_call("tavily.map")

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
