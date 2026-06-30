"""Tavily action: crawl — Deep site traversal."""
from __future__ import annotations

from core.contracts import ok, fail
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.bridge import _run_async
import tools.tavily_ops.client as _client
from tools.tavily_ops.errors import _handle_tavily_error, _assert_safe_urls


@register_action(
    "tavily", "crawl",
    help_text="""crawl — Deep site traversal. Requires API key.
Required: url
Optional: max_depth, max_breadth, limit, extract_depth, format""",
    examples=[
        'tavily(action="crawl", url="https://example.com")',
        'tavily(action="crawl", url="https://example.com", max_depth=3, extract_depth="advanced")',
    ],
)
def _action_crawl(
    url: str = "",
    query: str = "",
    max_depth: int = 2,
    max_breadth: int = 10,
    limit: int = 100,
    extract_depth: str = "basic",
    format: str = "markdown",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Execute Tavily crawl. Requires API key (keyless not supported)."""
    target_url = url or query
    if not target_url:
        return fail(
            "url or query is required for crawl action", trace_id=trace_id
        )

    err = _assert_safe_urls([target_url])
    if err:
        return fail(err, trace_id=trace_id)

    if _client._is_keyless():
        return fail(
            "crawl action requires a Tavily API key. "
            "Set TAVILY_API_KEY in .env or use search/extract instead.",
            trace_id=trace_id,
        )

    async def _call():
        client = _client._get_singleton_client()
        # SDK 0.7.26 uses 'instructions' not 'query' for crawl
        return await client.crawl(
            url=target_url,
            instructions=query if query else None,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            extract_depth=extract_depth,
            format=format,
        )

    try:
        result = _run_async(_call())
    except Exception as e:
        return _handle_tavily_error(e)

    response = ok(
        {"results": result.get("results", []), "keyless": False},
        trace_id=trace_id,
    )

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("tavily", response, trace_id)
