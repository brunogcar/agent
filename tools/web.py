"""
tools/web.py -- Web meta-tool.
Replaces: searxng MCP server + http MCP server + old scraping.py

The LLM sees ONE tool: web(action, ...)

Imports are lazy for bs4 (only on first call), but httpx is imported at top
to avoid "name not defined" errors in exception handlers and type checks.

Actions:
  search          -> query SearXNG, return ranked URLs + snippets
  scrape          -> fetch URL, return clean text (BS4, no JS/CSS noise)
  read            -> alias for scrape
  search_and_read -> search + scrape top results in parallel (ThreadPoolExecutor)

P1-1: Use per-request httpx.Client context manager instead of module-level client.
      This fixes connection leaks and thread-safety (gateway runs multiple threads).
M3:   Add 0.5s delay between requests in loop-based actions to be polite to servers.
P2:   Added URL deduplication to search_and_read to prevent scraping the same URL
      multiple times when SearXNG returns duplicates from different engines.
"""
from __future__ import annotations

import re
from typing import Optional
import time as _time

# ⭐ FIX: Import httpx at top level to avoid "name 'httpx' is not defined" errors
# in exception handlers and type checks (Python evaluates these at call time)
try:
    import httpx
except ImportError:
    # Graceful fallback - let the tool fail gracefully with a clear error
    raise ImportError(
        "httpx module is required for web.py but could not be imported. "
        "Please run: pip install httpx"
    )

from core.config import cfg
from registry import tool
import ipaddress
import socket
from urllib.parse import urlparse


# Module-level defaults (not clients)
MAX_TEXT_CHARS = 8000
SNIPPET_CHARS  = 300

_CLIENT_DEFAULTS = {
    "headers":          {"User-Agent": "Mozilla/5.0 MCP-Agent/1.0"},
    "timeout":          10.0,
    "follow_redirects": True,
}


def _is_safe_url(url: str) -> bool:
    """
    Return False if the URL resolves to a private, loopback, link-local,
    reserved, or multicast IP address (SSRF protection).
    """
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        # Resolve all addresses
        addrs = socket.getaddrinfo(hostname, None)
        for addr in addrs:
            ip = ipaddress.ip_address(addr[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_reserved or ip.is_multicast):
                return False
        return True
    except Exception:
        # If we can't validate, block (fail closed)
        return False


def _make_client():
    """Create a fresh httpx.Client. Always use as a context manager."""
    return httpx.Client(**_CLIENT_DEFAULTS)


def _get_client():
    """
    Legacy compatibility wrapper -- creates client on first call.
    New code should use _make_client() as context manager for thread safety.
    """
    return httpx.Client(**_CLIENT_DEFAULTS)


def _fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    """Fetch URL using context-managed client, return (html, error)."""
    # SSRF protection – block private/internal IPs before making the request
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
        raise  # never suppress shutdown signals
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _html_to_text(html: str, max_chars: int = MAX_TEXT_CHARS) -> tuple[str, str]:
    """Extract clean text from HTML using BeautifulSoup."""
    from bs4 import BeautifulSoup

    soup  = BeautifulSoup(html, "html.parser")
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

    text  = main.get_text(separator="\n", strip=True) if main else soup.get_text()
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

    clean     = "\n".join(filtered).strip()
    truncated = len(clean) > max_chars
    if truncated:
        clean = clean[:max_chars] + f"\n\n[...truncated at {max_chars} chars]"

    return clean, title


def _do_search(query: str, max_results: int = 5) -> dict:
    """Call SearXNG and return structured results."""
    try:
        with _make_client() as client:
            resp = client.get(
                f"{cfg.searxng_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=15,
            )
        resp.raise_for_status()
        data    = resp.json()
        raw     = data.get("results", [])[:max_results]
        results = []
        for r in raw:
            snippet = r.get("content", "") or r.get("description", "")
            results.append({
                "url":     r.get("url", ""),
                "title":   r.get("title", ""),
                "snippet": snippet[:SNIPPET_CHARS],
                "engine":  r.get("engine", ""),
            })
        return {"status": "success", "results": results,
                "count": len(results), "query": query}
    except httpx.TimeoutException:
        return {"status": "error", "error": f"SearXNG timeout at {cfg.searxng_url}"}
    except httpx.ConnectError:
        return {"status": "error", "error": f"Cannot reach SearXNG at {cfg.searxng_url}"}
    except Exception as e:
        return {"status": "error", "error": f"Search failed: {type(e).__name__}: {e}"}


def _do_scrape(url: str, max_chars: int = MAX_TEXT_CHARS) -> dict:
    """Fetch URL and return clean extracted text."""
    html, err = _fetch_html(url)
    if err:
        return {"status": "error", "url": url, "error": err}

    text, title = _html_to_text(html, max_chars)
    if not text:
        return {"status": "error", "url": url, "error": "No text content extracted"}

    return {
        "status":      "success",
        "url":        url,
        "title":      title,
        "text":       text,
        "word_count": len(text.split()),
        "truncated":   "[...truncated" in text,
    }


@tool
def web(
    action:      str,
    query:       str = "",
    url:         str = "",
    max_results: int = 5,
    max_chars:   int = MAX_TEXT_CHARS,
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
        Optional: max_chars (default 8000)
        Returns: {title, text, word_count, truncated}

    search_and_read
        Search then scrape the top results in parallel. One call for full research.
        Required: query
        Optional: max_results (default 5, max 10), max_chars
        Returns: {query, results: [{url, title, text}], scraped_count}

    Examples:
        web(action="search", query="FastMCP python tutorial", max_results=5)
        web(action="scrape", url="https://docs.python.org/3/library/pathlib.html")
        web(action="search_and_read", query="ChromaDB persistent client")
    """
    action = action.strip().lower()

    if action == "search":
        if not query:
            return {"status": "error", "error": "action='search' requires query="}
        return _do_search(query, max_results)

    if action in ("scrape", "read"):
        if not url:
            return {"status": "error",
                    "error": f"action='{action}' requires url="}
        return _do_scrape(url, max_chars)

    if action == "search_and_read":
        if not query:
            return {"status": "error",
                    "error": "action='search_and_read' requires query="}

        # [FIX] Allow up to 10 results for deep research (default is 5)
        n = min(max_results, 10)
        search_result = _do_search(query, n)
        if search_result["status"] != "success" or not search_result["results"]:
            return {"status": "error",
                    "error": search_result.get("error", "No search results"),
                    "query": query}

        # [P2] Deduplicate URLs while preserving rank order
        # SearXNG may return the same URL from different engines
        seen_urls = set()
        urls = []
        for r in search_result["results"]:
            u = r.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                urls.append(u)

        # Fetch all URLs in parallel -- reuses the same pattern as file(read_many)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(u: str) -> tuple[str, dict]:
            return u, _do_scrape(u, max_chars)

        results_map: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=min(len(urls), 4)) as ex:
            futures = {ex.submit(_fetch_one, u): u for u in urls}
            for future in as_completed(futures):
                u, result = future.result()
                results_map[u] = result

        # Rebuild in original rank order, keep only successful scrapes
        scraped = []
        for u in urls:
            result = results_map.get(u, {})
            if result.get("status") == "success" and result.get("text"):
                scraped.append({
                    "url":        u,
                    "title":      result.get("title", ""),
                    "text":       result["text"],
                    "word_count": result.get("word_count", 0),
                })

        return {
            "status":         "success",
            "query":         query,
            "results":       scraped,
            "scraped_count": len(scraped),
            "attempted":     len(urls),
            "duplicates_removed": len(search_result["results"]) - len(urls),
        }

    return {
        "status": "error",
        "error":  (
            f"Unknown action '{action}'. "
            "Use: search | scrape | read | search_and_read"
        ),
    }