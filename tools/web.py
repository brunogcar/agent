"""
tools/web.py — Web meta-tool.

Replaces: searxng MCP server + http MCP server + old scraping.py
The LLM sees ONE tool: web(action, ...)

Actions:
  search          → query SearXNG, return ranked URLs + snippets
  scrape          → fetch URL, return clean text (BS4, no JS/CSS noise)
  read            → alias for scrape (more intuitive name for the LLM)
  search_and_read → search + scrape top results in one call

Key improvements over old scraping.py:
  - httpx instead of urllib (connection pooling, better timeout handling)
  - BeautifulSoup4 removes <script>/<style> content before extraction
  - Proper text extraction (not raw HTML stripped with regex)
  - Returns structured metadata (title, url, word_count, truncated flag)
"""

from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from core.config import cfg
from registry import tool

# ── HTTP client (shared, connection-pooled) ───────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_client = httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True)

MAX_TEXT_CHARS = 8000   # max chars returned per page
SNIPPET_CHARS  = 300    # snippet length in search results


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    """
    Fetch URL, return (html, error).
    Returns ("", error_message) on failure.
    """
    try:
        resp = _client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text, ""
    except httpx.TimeoutException:
        return "", f"Timeout fetching {url}"
    except httpx.HTTPStatusError as e:
        return "", f"HTTP {e.response.status_code} from {url}"
    except httpx.ConnectError:
        return "", f"Cannot connect to {url}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _html_to_text(html: str, max_chars: int = MAX_TEXT_CHARS) -> tuple[str, str]:
    """
    Extract clean text from HTML using BeautifulSoup.
    Removes: <script>, <style>, <nav>, <footer>, <header>, <aside>
    Returns: (text, title)
    """
    soup  = BeautifulSoup(html, "html.parser")

    # Extract title before stripping tags
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer",
                     "header", "aside", "noscript", "iframe"]):
        tag.decompose()

    # Try to find main content block first
    main = (
        soup.find("main") or
        soup.find("article") or
        soup.find(id=re.compile(r"content|main|article", re.I)) or
        soup.find(class_=re.compile(r"content|main|article|post", re.I)) or
        soup.body or
        soup
    )

    text = main.get_text(separator="\n", strip=True) if main else soup.get_text()

    # Collapse excessive blank lines
    lines    = [ln.strip() for ln in text.splitlines()]
    filtered = []
    blanks   = 0
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
    """Call SearXNG and return structured results."""
    try:
        resp = _client.get(
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

        return {"status": "success", "results": results, "count": len(results), "query": query}

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
        "status":     "success",
        "url":        url,
        "title":      title,
        "text":       text,
        "word_count": len(text.split()),
        "truncated":  "[...truncated" in text,
    }


# ── Meta-tool ─────────────────────────────────────────────────────────────────

@tool
def web(
    action:      str,
    query:       str = "",
    url:         str = "",
    max_results: int = 5,
    max_chars:   int = MAX_TEXT_CHARS,
) -> dict:
    """
    Web tool — search the web or read web pages.

    action: "search" | "scrape" | "read" | "search_and_read"

    search
        Search SearXNG and return ranked URLs with titles and snippets.
        Required: query
        Optional: max_results (default 5)
        Returns:  {results: [{url, title, snippet, engine}], count}

    scrape / read
        Fetch a URL and return clean text (JavaScript and CSS removed).
        Required: url
        Optional: max_chars (default 8000)
        Returns:  {title, text, word_count, truncated}

    search_and_read
        Search then scrape the top results. One call for full research.
        Required: query
        Optional: max_results (default 3 for this action), max_chars
        Returns:  {query, results: [{url, title, text}], scraped_count}

    Examples:
        web(action="search", query="FastMCP python tutorial", max_results=5)
        web(action="scrape", url="https://docs.python.org/3/library/pathlib.html")
        web(action="search_and_read", query="ChromaDB persistent client", max_results=3)
    """
    action = action.strip().lower()

    # ── search ────────────────────────────────────────────────────────────────
    if action == "search":
        if not query:
            return {"status": "error", "error": "action='search' requires query="}
        return _do_search(query, max_results)

    # ── scrape / read ─────────────────────────────────────────────────────────
    if action in ("scrape", "read"):
        if not url:
            return {"status": "error", "error": f"action='{action}' requires url="}
        return _do_scrape(url, max_chars)

    # ── search_and_read ───────────────────────────────────────────────────────
    if action == "search_and_read":
        if not query:
            return {"status": "error", "error": "action='search_and_read' requires query="}

        n = min(max_results, 3)  # cap at 3 for this action to avoid long waits
        search_result = _do_search(query, n)

        if search_result["status"] != "success" or not search_result["results"]:
            return {
                "status": "error",
                "error":  search_result.get("error", "No search results"),
                "query":  query,
            }

        scraped  = []
        urls     = [r["url"] for r in search_result["results"] if r["url"]]

        for u in urls:
            result = _do_scrape(u, max_chars)
            if result["status"] == "success" and result.get("text"):
                scraped.append({
                    "url":        u,
                    "title":      result.get("title", ""),
                    "text":       result["text"],
                    "word_count": result.get("word_count", 0),
                })

        return {
            "status":        "success",
            "query":         query,
            "results":       scraped,
            "scraped_count": len(scraped),
            "attempted":     len(urls),
        }

    return {
        "status": "error",
        "error":  f"Unknown action '{action}'. Use: search | scrape | read | search_and_read",
    }
