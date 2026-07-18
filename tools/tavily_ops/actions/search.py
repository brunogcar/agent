"""tools/tavily_ops/actions/search.py — Tavily search action handler.

v1.2 FIXES:
- Pass coroutine factory (_call) not coroutine object (_call()) to resilience.
- Restore raw_content stripping when include_raw_content=False.
- Use core/net/errors for retry classification.
v1.3 FIXES:
- Wire core/net/default constants.
- Wire budget tracking (record_tool_call after success).
- Wire URL normalization (for cache key consistency).
"""
from __future__ import annotations

from typing import List, Optional

import tools.tavily_ops.client as _client
from core.contracts import fail, ok
from core.net.budget import record_tool_call, check_budget
from core.net.default import SEARCH_MAX_RESULTS
from core.net.url import normalize_url
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
    max_results: int = SEARCH_MAX_RESULTS,
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
    v1.3 CHANGES:
    - Wired default constants from core.net.default.
    - Wired budget tracking.
    """
    if not query:
        return fail("action='search' requires query=", trace_id=trace_id)

    if max_results < 1:
        return fail("max_results must be >= 1", trace_id=trace_id)
    if max_results > 20:
        return fail("max_results must be <= 20", trace_id=trace_id)

    # v1.3: Budget check
    if not check_budget("tavily.search"):
        return fail(
            "Tavily search budget exhausted. Try again tomorrow or use web(search).",
            trace_id=trace_id,
            error_code="QUOTA_EXHAUSTED",
        )

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
        error_result = _handle_tavily_error(e, trace_id=trace_id)
        # v1.6: Fallback to web(search) when Tavily is unavailable
        # (CB open, no API key, rate limited, or quota exhausted)
        if error_result.get("error_code") in ("CB_OPEN", "AUTH_FAILED", "RATE_LIMITED", "QUOTA_EXHAUSTED"):
            return _fallback_to_web_search(query, max_results, trace_id)
        return error_result

    # v1.2 FIX: Strip raw_content when not requested
    if not include_raw_content and "results" in result:
        for r in result.get("results", []):
            r.pop("raw_content", None)

    # v1.6: Deduplicate results by URL (preserves rank order — first occurrence wins)
    if "results" in result and result["results"]:
        seen_urls = set()
        deduped = []
        for r in result["results"]:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduped.append(r)
            elif not url:
                deduped.append(r)  # keep results without URL (shouldn't happen, but safe)
        result["results"] = deduped

    # v1.3: Record successful API call
    record_tool_call("tavily.search")

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



def _fallback_to_web_search(query: str, max_results: int, trace_id: str) -> dict:
    """v1.6: Fallback to web(search) when Tavily is unavailable.

    Called when Tavily returns CB_OPEN, AUTH_FAILED, RATE_LIMITED, or
    QUOTA_EXHAUSTED. Uses the web tool's SearXNG search as a graceful
    degradation path. The LLM sees a success response (not an error) so
    it can continue working without manual intervention.

    Returns the web search result (different shape from Tavily, but
    contains the same essential fields: results with url + title + content).
    """
    from core.tracer import tracer
    tracer.step(trace_id, "tavily_search",
                "Falling back to web(search) — Tavily unavailable")

    try:
        from tools.web import web
        result = web(action="search", query=query, max_results=max_results)
        if isinstance(result, dict) and result.get("status") == "success":
            # Add a note that this is a fallback
            data = result.get("data", result)
            if isinstance(data, dict):
                data["fallback"] = "web_search"
                data["note"] = "Tavily unavailable — results from SearXNG (web search)"
            return result
        return result  # Pass through web's error if it also failed
    except Exception as fallback_err:
        from core.contracts import fail
        return fail(
            f"Tavily unavailable and web search fallback also failed: {fallback_err}",
            trace_id=trace_id,
            error_code="FALLBACK_FAILED",
        )
