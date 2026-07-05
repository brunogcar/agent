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

    try:
        with _make_client() as client:
            resp = client.get(
                f"{searxng_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=SEARCH_TIMEOUT,  # [core/net] Was hardcoded 15
            )
            resp.raise_for_status()
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
    except httpx.TimeoutException:
        return fail(f"SearXNG timeout at {searxng_url}")
    except httpx.ConnectError:
        return fail(f"Cannot reach SearXNG at {searxng_url}")
    except Exception as e:
        return fail(f"Search failed: {type(e).__name__}: {e}")
