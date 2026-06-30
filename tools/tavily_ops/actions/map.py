"""Tavily action: map — Site structure discovery."""
from __future__ import annotations

from core.contracts import ok, fail
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.bridge import _run_async
import tools.tavily_ops.client as _client
from tools.tavily_ops.errors import _handle_tavily_error, _assert_safe_urls


@register_action(
    "tavily", "map",
    help_text="""map — Site structure discovery. Requires API key.
Required: url
Optional: max_depth, max_breadth, limit, query""",
    examples=[
        'tavily(action="map", url="https://example.com")',
        'tavily(action="map", url="https://example.com", query="API docs")',
    ],
)
def _action_map(
    url: str = "",
    query: str = "",
    max_depth: int = 2,
    max_breadth: int = 10,
    limit: int = 100,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Execute Tavily map. Requires API key (keyless not supported)."""
    target_url = url or query
    if not target_url:
        return fail(
            "url or query is required for map action", trace_id=trace_id
        )

    err = _assert_safe_urls([target_url])
    if err:
        return fail(err, trace_id=trace_id)

    if _client._is_keyless():
        return fail(
            "map action requires a Tavily API key. "
            "Set TAVILY_API_KEY in .env or use search/extract instead.",
            trace_id=trace_id,
        )

    async def _call():
        client = _client._get_singleton_client()
        # SDK 0.7.26 uses 'instructions' not 'query' for map
        return await client.map(
            url=target_url,
            instructions=query if query else None,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
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
