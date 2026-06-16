"""
tools/web.py -- Web meta-tool.
Replaces: searxng MCP server + http MCP server + old scraping.py
The LLM sees ONE tool: web(action, ...)

Imports are lazy for bs4 (only on first call), but httpx is imported at top
to avoid "name not defined" errors in exception handlers and type checks.

Actions:
  search -> query SearXNG, return ranked URLs + snippets
  scrape -> fetch URL, return clean text (BS4, no JS/CSS noise)
  read   -> alias for scrape
  search_and_read -> search + scrape top results in parallel (ThreadPoolExecutor)

P1-1: Use per-request httpx.Client context manager instead of module-level client.
  This fixes connection leaks and thread-safety (gateway runs multiple threads).
M3: Add 0.5s delay between requests in loop-based actions to be polite to servers.
P2: Added URL deduplication to search_and_read to prevent scraping the same URL
  multiple times when SearXNG returns duplicates from different engines.
P2: Magic numbers centralized in core/config.py.
"""
from __future__ import annotations

import atexit
import re
import threading
import time as _time
from typing import Optional
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    raise ImportError(
        "httpx module is required for web.py but could not be imported. "
        "Please run: pip install httpx"
    )

import logging
from core.config import cfg
from registry import tool
from core.contracts import ok, fail

logger = logging.getLogger(__name__)

# [P2] Magic numbers centralized in core/config.py
# cfg.web_max_text_chars, cfg.web_snippet_chars, cfg.web_max_search_results

_CLIENT_DEFAULTS = {
    "headers": {"User-Agent": "Mozilla/5.0 MCP-Agent/1.0"},
    "timeout": 10.0,
    "follow_redirects": True,
}

# [BUGFIX-6] Module-level singleton httpx.Client with connection pooling.
# Replaces per-request fresh Client() to avoid TCP/TLS handshake overhead.
# httpx.Client is thread-safe; ThreadPoolExecutor in search_and_read is safe.
_HTTP_CLIENT: Optional[httpx.Client] = None
_HTTP_CLIENT_LOCK = threading.Lock()


def _get_singleton_client() -> httpx.Client:
    """Return the singleton httpx.Client, creating it on first call."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        with _HTTP_CLIENT_LOCK:
            if _HTTP_CLIENT is None:
                _HTTP_CLIENT = httpx.Client(
                    **_CLIENT_DEFAULTS,
                    limits=httpx.Limits(max_connections=20),
                )
    return _HTTP_CLIENT


def _close_client() -> None:
    """Close the singleton client on process exit."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        try:
            _HTTP_CLIENT.close()
        except Exception:
            pass
        _HTTP_CLIENT = None


atexit.register(_close_client)


class _SingletonClientContext:
    """Context manager that yields the singleton client without closing it."""
    def __enter__(self):
        return _get_singleton_client()
    def __exit__(self, *args):
        pass  # Singleton stays alive


def _make_client():
    """Return a context manager yielding the pooled singleton client."""
    return _SingletonClientContext()


def _get_client():
    """Legacy compatibility wrapper — returns the singleton client."""
    return _get_singleton_client()


def _is_safe_url(url: str) -> bool:
    """
    Return False if the URL resolves to a private, loopback, link-local,
    reserved, or multicast IP address (SSRF protection).
    """
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        # SSRF helper imported from centralized core.security
        from core.security import is_safe_network_address
        return is_safe_network_address(hostname)
    except Exception:
        return False


def _fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    """Fetch URL using pooled client, return (html, error)."""
    if not _is_safe_url(url):
        return "", f"Blocked for security: {url} resolves to a private/internal address"

    try:
        with _make_client() as client:
            resp = client.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text, ""
    except httpx.TimeoutException:
        return "", f"Timeout fetching {url}"
    except httpx.HTTPStatusError as e:
        return "", f"HTTP {e.response.status_code} from {url}"
    except httpx.ConnectError:
        return "", f"Cannot connect to {url}"
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _html_to_text(html: str, max_chars: Optional[int] = None) -> tuple[str, str]:
    """Extract clean text from HTML using BeautifulSoup."""
    if max_chars is None:
        max_chars = cfg.web_max_text_chars

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    for tag in soup(["script", "style", "nav", "footer",
                     "header", "aside", "noscript", "iframe"]):
        tag.decompose()

    main = (
        soup.find("main") or
        soup.find("article") or
        soup.find(id=re.compile(r"content|main|article", re.I)) or
        soup.find(class_=re.compile(r"content|main|article|post", re.I)) or
        soup.body or soup
    )

    text = main.get_text(separator="\n", strip=True) if main else soup.get_text()
    lines = [ln.strip() for ln in text.splitlines()]
    filtered, blanks = [], 0
    for ln in lines:
        if ln:
            filtered.append(ln)
            blanks = 0
        else:
            blanks += 1
            if blanks <= 2:
                filtered.append("")

    clean = "\n".join(filtered).strip()
    truncated = len(clean) > max_chars
    if truncated:
        clean = clean[:max_chars] + f"\n\n[...truncated at {max_chars} chars]"

    return clean, title


def _do_search(query: str, max_results: int = 5) -> dict:
    """Call SearXNG and return structured results. Default 5 for backward compat."""
    try:
        with _make_client() as client:
            resp = client.get(
                f"{cfg.searxng_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=15,
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
            return ok({"results": results,
                       "count": len(results), "query": query})
    except httpx.TimeoutException:
        return fail(f"SearXNG timeout at {cfg.searxng_url}")
    except httpx.ConnectError:
        return fail(f"Cannot reach SearXNG at {cfg.searxng_url}")
    except Exception as e:
        return fail(f"Search failed: {type(e).__name__}: {e}")


def _do_scrape(url: str, max_chars: Optional[int] = None) -> dict:
    """Fetch URL and return clean extracted text."""
    if max_chars is None:
        max_chars = cfg.web_max_text_chars

    html, err = _fetch_html(url)
    if err:
        return fail(err, url=url)

    text, title = _html_to_text(html, max_chars)
    if not text:
        return fail("No text content extracted", url=url)

    return ok({
        "url": url,
        "title": title,
        "text": text,
        "word_count": len(text.split()),
        "truncated": "[...truncated" in text,
    })


@tool
def web(
    action: str,
    query: str = "",
    url: str = "",
    max_results: int = 5,
    max_chars: Optional[int] = None,
    trace_id: str = "",
) -> dict:
    """
    Web tool -- search the web or read web pages.

    action: "search" | "scrape" | "read" | "search_and_read"

    search
      Search SearXNG and return ranked URLs with titles and snippets.
      Required: query
      Optional: max_results (default 5)
      Returns: {results: [{url, title, snippet, engine}], count}

    scrape / read
      Fetch a URL and return clean text (JavaScript and CSS removed).
      Required: url
      Optional: max_chars (default from cfg.web_max_text_chars)
      Returns: {title, text, word_count, truncated}

    search_and_read
      Search then scrape the top results in parallel. One call for full research.
      Required: query
      Optional: max_results (default 5, upper bound from cfg.web_max_search_results), max_chars
      Returns: {query, results: [{url, title, text}], scraped_count}

    Examples:
      web(action="search", query="FastMCP python tutorial", max_results=5)
      web(action="scrape", url="https://docs.python.org/3/library/pathlib.html")
      web(action="search_and_read", query="ChromaDB persistent client")
    """
    if max_chars is None:
        max_chars = cfg.web_max_text_chars

    action = action.strip().lower()

    if action == "search":
        if not query:
            return fail("action='search' requires query=")
        return _do_search(query, max_results)

    if action in ("scrape", "read"):
        if not url:
            return {"status": "error",
                    "error": f"action='{action}' requires url="}
        result = _do_scrape(url, max_chars)
        from core.memory_backend.pruner import prune_tool_dict
        return prune_tool_dict("web", result, trace_id)

    if action == "search_and_read":
        if not query:
            return fail("action='search_and_read' requires query=")

        # [P2] Upper bound from config (default 10, allows deep research up to cfg limit)
        n = min(max_results, cfg.web_max_search_results)
        search_result = _do_search(query, n)
        if search_result.get("status") != "success" or not search_result.get("data", {}).get("results", []):
            return fail(search_result.get("error") or "No search results", query=query)

        # [P2] Deduplicate URLs while preserving rank order
        seen_urls = set()
        urls = []
        for r in search_result.get("data", {}).get("results", []):
            u = r.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                urls.append(u)

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(u: str) -> tuple[str, dict]:
            return u, _do_scrape(u, max_chars)

        results_map: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=min(len(urls), 4)) as ex:
            futures = {ex.submit(_fetch_one, u): u for u in urls}
            for future in as_completed(futures):
                u, result = future.result()
                results_map[u] = result

        scraped = []
        for u in urls:
            result = results_map.get(u, {})
            if result.get("status") == "success" and result.get("data", {}).get("text"):
                scraped.append({
                    "url": u,
                    "title": result.get("data", {}).get("title", ""),
                    "text": result["data"]["text"],
                    "word_count": result.get("data", {}).get("word_count", 0),
                })

        result = ok({
            "query": query,
            "results": scraped,
            "scraped_count": len(scraped),
            "attempted": len(urls),
            "duplicates_removed": len(search_result.get("data", {}).get("results", [])) - len(urls),
        })
        from core.memory_backend.pruner import prune_tool_dict
        return prune_tool_dict("web", result, trace_id)

    return fail(
        f"Unknown action '{action}'. "
        "Use: search | scrape | read | search_and_read"
    )
