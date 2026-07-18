"""Web action: search — Query SearXNG and return ranked results.

[core/net adoption] Now uses SEARCH_TIMEOUT from core/net/default.py (was hardcoded 15).
"""
from __future__ import annotations

import httpx

from core.config import cfg
from core.contracts import fail, ok
from core.net.default import SEARCH_TIMEOUT
from tools.web_ops._registry import register_action
from tools.web_ops.client import _make_client
from tools.web_ops.utils import _is_safe_url


@register_action(
    "web",
    "search",
    help_text="""search — Query SearXNG and return ranked URLs with titles and snippets.
Required: query
Optional: max_results (default 5)""",
    examples=[
        'web(action="search", query="FastMCP python tutorial")',
        'web(action="search", query="ChromaDB persistent client", max_results=10)',
    ],
)
def _action_search(
    query: str = "",
    max_results: int = 5,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Call SearXNG and return structured search results.

    Default max_results=5 for backward compatibility.
    SSRF-guards the SearXNG instance URL itself before any request.
    """
    if not query:
        return fail("action='search' requires query=")

    # Guard the SearXNG endpoint against SSRF (e.g., cfg pointing to 192.168.x.x)
    searxng_url = cfg.searxng_url
    if not _is_safe_url(searxng_url):
        return fail(
            f"SSRF blocked: SearXNG URL {searxng_url} resolves to a private/internal address"
        )

    # v1.4: Use retry_sync + classify_http_error (was: bare raise_for_status + inline except)
    from core.net.retry import retry_sync
    from core.net.errors import classify_http_error, is_retryable_error

    def _do_search():
        with _make_client() as client:
            resp = client.get(
                f"{searxng_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=SEARCH_TIMEOUT,
            )
            resp.raise_for_status()
            return resp

    try:
        resp = retry_sync(_do_search, max_retries=2, base_delay=1.0, max_delay=5.0)
        data = resp.json()
        raw = data.get("results", [])[:max_results]
        results = []
        for r in raw:
            snippet = r.get("content", "") or r.get("description", "")
            results.append({
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": snippet[:cfg.web_snippet_chars],
                "engine": r.get("engine", ""),
            })
        return ok({
            "results": results,
            "count": len(results),
            "query": query,
        })
    except Exception as e:
        # v1.4: Use classify_http_error for structured error codes
        error_code = classify_http_error(e)  # returns str, not tuple
        return fail(
            f"SearXNG search failed ({error_code}): {type(e).__name__}: {e}",
            trace_id=trace_id,
            error_code=error_code,
        )
