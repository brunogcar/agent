"""Web action: crawl — Fetch a URL via crawl4ai and return clean LLM-ready markdown.

v1.3 NEW — Prototype action for evaluating crawl4ai integration.

WHY THIS EXISTS:
  The current scrape pipeline uses BeautifulSoup (fails on JS-heavy pages) with
  a browser fallback (slow — 2 calls: navigate + text_content). Crawl4ai handles
  JS natively and returns clean markdown in a single call. This action is a
  prototype to evaluate whether crawl4ai should replace the scrape + browser
  fallback chain in the research workflow.

  See:
    - docs/tools/web/CHANGELOG.md → v1.3 entry
    - docs/tools/TOOLS.md → "Crawl4ai integration" section
    - docs/workflows/research/CHANGELOG.md → roadmap (potential refactor)
    - docs/workflows/deep_research/CHANGELOG.md → roadmap (potential refactor)

SOFT DEPENDENCY:
  crawl4ai is imported lazily inside _action_crawl(). If not installed, returns
  a clear error: "crawl4ai is not installed. Run `pip install crawl4ai`".
  Non-crawl web actions (search, scrape, read, search_and_read) work fine
  without it.

ASYNC→SYNC BRIDGE:
  crawl4ai is async-first (AsyncWebCrawler). This handler runs it via
  asyncio.run() in a thread to avoid event loop conflicts with the MCP server
  (which may have its own loop). This is the same pattern the understand
  workflow used before its v1.0 sync conversion.

LLM EXTRACTION (optional):
  crawl4ai supports LLM-based structured extraction (CSS/XPath selectors or
  LLM schema). This prototype does NOT use LLM extraction — it returns clean
  markdown only. LLM extraction would require transformers/PyTorch (heavy deps)
  and is deferred. See docs/tools/web/CHANGELOG.md roadmap.

FALLBACK:
  If crawl4ai fails (not installed, page timeout, JS error), this action does
  NOT fall back to scrape. It returns an error. The caller can retry with
  web(action="scrape") or browser(action="text_content") explicitly.
  Automatic fallback would hide crawl4ai failures and defeat the evaluation
  purpose of this prototype.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from core.config import cfg
from core.contracts import fail, ok
from tools.web_ops._registry import register_action
from tools.web_ops.utils import _is_safe_url


@register_action(
    "web",
    "crawl",
    help_text="""crawl — Fetch a URL via crawl4ai and return clean LLM-ready markdown.
Handles JS-heavy pages natively (React/Angular/Vue SPAs). Returns markdown,
not raw HTML. Prototype action for evaluating crawl4ai integration.

Required: url
Optional: max_chars (default from cfg.web_max_text_chars)

Soft dependency: crawl4ai must be installed (pip install crawl4ai).
If not installed, returns a clear error. Does NOT fall back to scrape.

When to use:
  - JS-heavy pages (React/Angular/Vue SPAs) where web(scrape) returns empty/garbage
  - Pages where you'd otherwise use browser(text_content) as fallback
  - When you need clean markdown for LLM consumption (not raw HTML)

When NOT to use:
  - Static pages (use web(scrape) — faster, no JS execution overhead)
  - Interactive automation (use browser(click/fill/navigate))
  - Search (use web(search) or tavily(search))
""",
    examples=[
        'web(action="crawl", url="https://react-app-example.com")',
        'web(action="crawl", url="https://docs.example.com", max_chars=10000)',
    ],
)
def _action_crawl(
    url: str = "",
    max_chars: Optional[int] = None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Fetch URL via crawl4ai and return clean markdown.

    Handles JS-heavy pages natively. Returns markdown (not HTML).
    Soft dependency on crawl4ai — lazy import.
    """
    if not url:
        return fail("action='crawl' requires url=")

    if max_chars is None:
        max_chars = cfg.web_max_text_chars

    # SSRF check — same guard as scrape. _is_safe_url returns bool (not tuple).
    if not _is_safe_url(url):
        return fail(f"Blocked for security: {url} resolves to a private/internal address", url=url)

    # Lazy import — crawl4ai is a soft dependency
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        return fail(
            "crawl4ai is not installed. Run `pip install crawl4ai` to use "
            "web(action='crawl'). Non-crawl web actions work fine without it.",
            url=url,
        )

    # Run async crawler in a thread to avoid event loop conflicts with MCP server
    try:
        markdown, title = _run_crawl_async(url, AsyncWebCrawler)
    except Exception as e:
        return fail(f"crawl4ai failed: {e}", url=url)

    if not markdown or not markdown.strip():
        return fail("crawl4ai returned empty content — page may be blocked or empty", url=url)

    # Truncate to max_chars (same behavior as scrape)
    truncated = False
    if len(markdown) > max_chars:
        markdown = markdown[:max_chars] + f"\n\n[...truncated — {len(markdown)} chars total]"
        truncated = True

    return ok({
        "url": url,
        "title": title,
        "text": markdown,
        "word_count": len(markdown.split()),
        "truncated": truncated,
        "format": "markdown",  # distinguishes from scrape (which returns plain text)
        "crawler": "crawl4ai",
    }, trace_id=trace_id)


def _run_crawl_async(url: str, crawler_class) -> tuple[str, str]:
    """Run crawl4ai's AsyncWebCrawler in a dedicated event loop.

    Runs in a thread to avoid conflicting with any existing event loop
    (the MCP server may have one). Returns (markdown, title).

    Args:
        url: URL to crawl.
        crawler_class: The AsyncWebCrawler class (passed from caller — the
            import happens in _action_crawl so the soft-dependency check
            returns a clean error if crawl4ai is missing).

    Raises any exception from crawl4ai — the caller wraps it in fail().
    """
    def _crawl():
        async def _async_crawl():
            async with crawler_class() as crawler:
                result = await crawler.arun(url=url)
                if result and result.markdown:
                    # crawl4ai returns a markdown string; title may be in metadata
                    title = ""
                    if hasattr(result, "metadata") and result.metadata:
                        title = result.metadata.get("title", "") or ""
                    return result.markdown, title
                return "", ""
        return asyncio.run(_async_crawl())

    # Run in a fresh thread to avoid "event loop already running" errors
    import threading
    result_holder: dict = {}
    def _target():
        try:
            result_holder["result"] = _crawl()
        except Exception as e:
            result_holder["error"] = e

    t = threading.Thread(target=_target)
    t.start()
    t.join(timeout=120)  # 2-minute hard cap

    if t.is_alive():
        return "", ""
    if "error" in result_holder:
        raise result_holder["error"]
    return result_holder.get("result", ("", ""))
