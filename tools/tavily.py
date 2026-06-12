"""
tools/tavily.py — Tavily AI research tool.
Async client wrapped in sync @tool facade for MCP compatibility.

Actions (exposed to LLM):
  search   — AI-ranked web search with citations
  extract  — Bulk URL content extraction
  crawl    — Deep site traversal
  map      — Site structure discovery

research action is implemented as _do_research() but NOT exposed in the
@tool DISPATCH dict. Reserved for workflows/deep_research.py.
See docs/TAVILY.md for full documentation.

Keyless mode: AsyncTavilyClient() with no API key supports search and
extract with lower limits. Response includes "keyless": true.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Optional
from urllib.parse import urlparse

from registry import tool
from core.config import cfg
from core.contracts import ok, fail
from core.security import is_safe_network_address

logger = logging.getLogger(__name__)

# Module-level flag for parallel dispatcher
PARALLEL_SAFE = True

# ── Async-to-Sync Bridge ───────────────────────────────────────────────────

def _run_async(coro):
    """
    Run an async coroutine from a sync context.
    Handles the case where a thread may or may not have a running event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Running loop exists — run in fresh thread to avoid nested loop error
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(asyncio.run, coro)
        return future.result(timeout=cfg.tavily_timeout + 10)

# ── Lazy Client ────────────────────────────────────────────────────────────

_tavily_client = None


def _get_client():
    """Lazy-load AsyncTavilyClient. Keyless if no API key configured."""
    global _tavily_client
    if _tavily_client is None:
        try:
            from tavily import AsyncTavilyClient
        except ImportError as e:
            raise ImportError(
                "tavily-python not installed. Run: pip install tavily-python"
            ) from e
        api_key = cfg.tavily_api_key or None
        _tavily_client = AsyncTavilyClient(api_key=api_key)
    return _tavily_client


def _is_keyless() -> bool:
    """Return True if running without an API key."""
    return not bool(cfg.tavily_api_key)


# ── SSRF Guard ─────────────────────────────────────────────────────────────

def _assert_safe_urls(urls: list[str]) -> Optional[str]:
    """Return error string if any URL is unsafe, else None."""
    for url in urls:
        hostname = urlparse(url).hostname or ""
        if not is_safe_network_address(hostname):
            return f"Blocked: {url} resolves to a private/internal address"
    return None


# ── Action Implementations ─────────────────────────────────────────────────

def _do_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: Optional[str] = None,
    time_range: Optional[str] = None,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    include_answer: bool = True,
    include_raw_content: bool = False,
) -> dict:
    """Execute Tavily search and return pruned result."""
    keyless = _is_keyless()

    # Cap max_results in keyless mode
    if keyless and max_results > 3:
        max_results = 3

    async def _call():
        client = _get_client()
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

    # Strip raw_content by default unless explicitly requested
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
        trace_id="",
    )

    from core.memory_backend.pruner import prune_tool_dict

    return prune_tool_dict("tavily", response, "")


def _do_extract(
    urls: list[str],
    include_images: bool = False,
    extract_depth: str = "basic",
    format: str = "markdown",
) -> dict:
    """Execute Tavily extract and return pruned result."""
    err = _assert_safe_urls(urls)
    if err:
        return fail(err)

    keyless = _is_keyless()

    async def _call():
        client = _get_client()
        return await client.extract(
            urls=urls,
            include_images=include_images,
            extract_depth=extract_depth,
            format=format,
        )

    try:
        result = _run_async(_call())
    except Exception as e:
        return _handle_tavily_error(e)

    response = ok(
        {"results": result.get("results", []), "keyless": keyless},
        trace_id="",
    )

    from core.memory_backend.pruner import prune_tool_dict

    return prune_tool_dict("tavily", response, "")


def _do_crawl(
    url: str,
    max_depth: int = 2,
    max_breadth: int = 10,
    limit: int = 100,
) -> dict:
    """Execute Tavily crawl. Requires API key (keyless not supported)."""
    err = _assert_safe_urls([url])
    if err:
        return fail(err)

    if _is_keyless():
        return fail(
            "crawl action requires a Tavily API key. "
            "Set TAVILY_API_KEY in .env or use search/extract instead."
        )

    async def _call():
        client = _get_client()
        return await client.crawl(
            url=url,
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
        trace_id="",
    )

    from core.memory_backend.pruner import prune_tool_dict

    return prune_tool_dict("tavily", response, "")


def _do_map(
    url: str,
    max_depth: int = 2,
    max_breadth: int = 10,
    limit: int = 100,
    query: Optional[str] = None,
) -> dict:
    """Execute Tavily map. Requires API key (keyless not supported)."""
    err = _assert_safe_urls([url])
    if err:
        return fail(err)

    if _is_keyless():
        return fail(
            "map action requires a Tavily API key. "
            "Set TAVILY_API_KEY in .env or use search/extract instead."
        )

    async def _call():
        client = _get_client()
        return await client.map(
            url=url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            query=query,
        )

    try:
        result = _run_async(_call())
    except Exception as e:
        return _handle_tavily_error(e)

    response = ok(
        {"results": result.get("results", []), "keyless": False},
        trace_id="",
    )

    from core.memory_backend.pruner import prune_tool_dict

    return prune_tool_dict("tavily", response, "")


def _do_research(
    input: str,
    model: Optional[str] = None,
    citation_format: str = "apa",
) -> dict:
    """
    Execute Tavily research (end-to-end deep research).
    NOT exposed in the @tool DISPATCH — reserved for workflow use.
    """
    if _is_keyless():
        return fail(
            "research action requires a Tavily API key. "
            "Set TAVILY_API_KEY in .env."
        )

    async def _call():
        client = _get_client()
        return await client.research(
            input=input,
            model=model,
            citation_format=citation_format,
        )

    try:
        result = _run_async(_call())
    except Exception as e:
        return _handle_tavily_error(e)

    from core.memory_backend.pruner import prune_tool_dict

    response = ok(
        {
            "answer": result.get("answer", ""),
            "citations": result.get("citations", []),
            "keyless": False,
        },
        trace_id="",
    )
    return prune_tool_dict("tavily", response, "")


# ── Error Handling ─────────────────────────────────────────────────────────

def _handle_tavily_error(e: Exception) -> dict:
    """Map Tavily and network exceptions to standardized fail responses."""
    error_type = type(e).__name__
    error_msg = str(e)

    # Tavily-specific exceptions (imported lazily to avoid hard dependency)
    try:
        from tavily.errors import (
            TavilyAPIError,
            TavilyKeylessLimitError,
            InvalidAPIKeyError,
            UsageLimitExceededError,
        )
    except ImportError:
        TavilyAPIError = TavilyKeylessLimitError = InvalidAPIKeyError = UsageLimitExceededError = None

    if TavilyKeylessLimitError and isinstance(e, TavilyKeylessLimitError):
        return fail(
            "Tavily keyless rate limit reached. Set TAVILY_API_KEY in .env for higher limits."
        )

    if InvalidAPIKeyError and isinstance(e, InvalidAPIKeyError):
        return fail(
            "Tavily API key invalid or revoked. Check TAVILY_API_KEY in .env."
        )

    if UsageLimitExceededError and isinstance(e, UsageLimitExceededError):
        return fail("Tavily monthly quota exhausted.")

    if TavilyAPIError and isinstance(e, TavilyAPIError):
        status = getattr(e, "status_code", 0)
        if status == 429:
            import time

            time.sleep(2)
            return fail("Tavily rate limit exceeded (HTTP 429). Retry failed.")
        return fail(f"Tavily API error ({status}): {error_msg[:200]}")

    # httpx network errors
    try:
        import httpx
    except ImportError:
        httpx = None

    if httpx:
        if isinstance(e, httpx.TimeoutException):
            return fail(f"Tavily request timed out after {cfg.tavily_timeout}s.")
        if isinstance(e, httpx.ConnectError):
            return fail("Failed to connect to Tavily API. Check network.")
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code if hasattr(e, "response") else 0
            if status == 429:
                return fail("Tavily rate limit exceeded (HTTP 429).")
            if status in (401, 403):
                return fail("Tavily authentication failed. Check API key.")
            return fail(f"Tavily HTTP error {status}: {error_msg[:200]}")

    return fail(f"Tavily error: {error_type}: {error_msg[:200]}")


# ── Tool Facade ─────────────────────────────────────────────────────────────

@tool
def tavily(
    action: str,
    query: str = "",
    urls: Optional[list[str]] = None,
    url: str = "",
    input: str = "",
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
    model: Optional[str] = None,
    citation_format: str = "apa",
    trace_id: str = "",
) -> dict:
    """
    Tavily AI research tool — AI-ranked search, extraction, and deep research.

    WHEN TO USE THIS TOOL:
    | Need | Tool | Why |
    |------|------|-----|
    | Quick search (5-10 results) | web(search) | Fast, uses SearXNG, no API costs |
    | AI-ranked search | tavily(search) | Better relevance, citations, AI answer |
    | Single page text (static) | web(read) | Simple, no JS, no API costs |
    | Bulk URL extraction | tavily(extract) | Optimized for batch, AI-powered |
    | Site crawling | tavily(crawl) | Follows links, discovers pages |
    | Site structure | tavily(map) | Discovers site hierarchy |
    | JS page text | browser(navigate+text_content) | Renders JavaScript |
    | Interactive forms | browser(click, fill) | Supports user interaction |

    ACTIONS:
    search: AI-ranked web search
      query (required): Search query
      max_results (default: 5): Number of results (1-10, capped at 3 in keyless)
      search_depth (default: "basic"): "basic" or "advanced"
      include_answer (default: True): Include AI-generated answer

    extract: Bulk URL content extraction
      urls (required): List of URLs (max 10)
      include_images (default: False): Include images in results
      format (default: "markdown"): "markdown" or "text"

    crawl: Deep site traversal
      url (required): Starting URL
      max_depth (default: 2): Maximum link depth (1-3)
      max_breadth (default: 10): Maximum pages per level
      limit (default: 100): Maximum total pages

    map: Site structure discovery
      url (required): Starting URL
      max_depth (default: 2): Maximum link depth
      query (optional): Focus on pages matching this query

    NOTE: The "research" action (end-to-end deep research) is not exposed
    as a tool action. Use the deep_research workflow for that capability.

    Requires TAVILY_API_KEY in .env for full functionality. Keyless mode
    supports search and extract with lower limits.
    """
    action = action.strip().lower()

    if action == "search":
        if not query:
            return fail("query is required for search action", trace_id=trace_id)
        return _do_search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            topic=topic,
            time_range=time_range,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
        )

    if action == "extract":
        if not urls:
            return fail("urls is required for extract action", trace_id=trace_id)
        if len(urls) > 10:
            return fail("urls cannot exceed 10 items", trace_id=trace_id)
        return _do_extract(
            urls=urls,
            include_images=include_images,
            extract_depth=extract_depth,
            format=format,
        )

    if action == "crawl":
        target_url = url or query
        if not target_url:
            return fail(
                "url or query is required for crawl action", trace_id=trace_id
            )
        return _do_crawl(
            url=target_url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
        )

    if action == "map":
        target_url = url or query
        if not target_url:
            return fail(
                "url or query is required for map action", trace_id=trace_id
            )
        return _do_map(
            url=target_url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            query=query,
        )

    return fail(
        f"Unknown action '{action}'. Use: search | extract | crawl | map",
        trace_id=trace_id,
    )
