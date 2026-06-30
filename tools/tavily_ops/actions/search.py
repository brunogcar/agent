"""Tavily action: search — AI-ranked web search with citations."""
from __future__ import annotations
from typing import Optional

from core.contracts import ok, fail
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.bridge import _run_async
import tools.tavily_ops.client as _client
from tools.tavily_ops.errors import _handle_tavily_error


@register_action(
    "tavily", "search",
    help_text="""search — AI-ranked web search with citations.
Required: query
Optional: max_results (1-10, capped at 3 keyless), search_depth, topic,
  time_range, include_domains, exclude_domains, include_answer,
  include_raw_content""",
    examples=[
        'tavily(action="search", query="FastMCP python tutorial")',
        'tavily(action="search", query="...", search_depth="advanced", max_results=10)',
    ],
)
def _action_search(
    query: str = "",
    max_results: int = 5,
    search_depth: str = "basic",
    topic: Optional[str] = None,
    time_range: Optional[str] = None,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    include_answer: bool = True,
    include_raw_content: bool = False,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Execute Tavily search and return pruned result."""
    if not query:
        return fail("query is required for search action", trace_id=trace_id)

    keyless = _client._is_keyless()
    if keyless:
        _client._warn_keyless_once()
    if keyless and max_results > 3:
        max_results = 3

    async def _call():
        client = _client._get_singleton_client()
        return await client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            topic=topic,
            time_range=time_range,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            include_answer=include_answer,
            include_raw_content=include_raw_content,
        )

    try:
        result = _run_async(_call())
    except Exception as e:
        return _handle_tavily_error(e)

    if not include_raw_content and "results" in result:
        for r in result.get("results", []):
            r.pop("raw_content", None)

    response = ok(
        {
            "results": result.get("results", []),
            "answer": result.get("answer", ""),
            "query": query,
            "keyless": keyless,
        },
        trace_id=trace_id,
    )

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("tavily", response, trace_id)
