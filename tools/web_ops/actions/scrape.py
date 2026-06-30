"""Web action: scrape — Fetch a URL and return clean extracted text.

Includes _fetch_html() and _html_to_text() helpers. These are private to
this module; other actions that need scraping should call _action_scrape().
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

from core.config import cfg
from core.contracts import fail, ok
from tools.web_ops._registry import register_action
from tools.web_ops.client import _make_client
from tools.web_ops.utils import _is_safe_url


@register_action(
    "web",
    "scrape",
    help_text="""scrape — Fetch a URL and return clean extracted text (no pruning).
Required: url
Optional: max_chars (default from cfg.web_max_text_chars)
Note: For standard page reading, use 'read' instead.""",
    examples=[
        'web(action="scrape", url="https://docs.python.org/3/library/pathlib.html")',
    ],
)
def _action_scrape(
    url: str = "",
    max_chars: Optional[int] = None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Fetch URL and return clean extracted text.

    Returns the full text up to max_chars without pruning.
    Use _action_read (the facade) for pruned output with artifact storage.
    """
    if not url:
        return fail("action='scrape' requires url=")

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


def _fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    """Fetch URL using the pooled singleton client, return (html, error).

    SSRF guard is applied before any HTTP request.
    """
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
    """Extract clean text from HTML using BeautifulSoup.

    Decomposes script, style, nav, footer, header, aside, noscript, iframe.
    Prefers <main> or <article> tags; falls back to body or full soup.
    Collapses blank lines to at most 2 consecutive newlines.

    Returns:
        (clean_text, title)
    """
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
