"""Web action: scrape — Fetch a URL and return clean extracted text.

Includes _fetch_html() and _html_to_text() helpers. These are private to
this module; other actions that need scraping should call _action_scrape().
"""
from __future__ import annotations

import re
import time
from typing import Optional

import httpx

from core.config import cfg
from core.contracts import fail, ok
from tools.web_ops._registry import register_action
from tools.web_ops.client import _make_client, _pick_user_agent
from tools.web_ops.utils import _is_safe_url

# Hard ceiling: reject responses larger than 10 MB before reading body.
_MAX_RESPONSE_SIZE_BYTES = 10 * 1024 * 1024

# Max retry attempts for transient failures (total tries = 1 + _MAX_RETRIES).
_MAX_RETRIES = 1

# Retryable status codes and exceptions.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
)


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

    Applies SSRF guard, response-size guard, content-type guard, and
    one retry with exponential backoff on transient errors.
    Per-request User-Agent rotation to reduce 403 blocks.
    """
    if not _is_safe_url(url):
        return "", f"Blocked for security: {url} resolves to a private/internal address"

    # Pre-flight PDF detection by URL extension
    if url.lower().rstrip("/").endswith(".pdf"):
        return "", (
            f"URL appears to be a PDF: {url}. "
            "Use file(action='read_pdf') or download to workspace/.artifacts/ instead."
        )

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with _make_client() as client:
                # Per-request UA rotation — overrides singleton default
                resp = client.get(
                    url,
                    timeout=timeout,
                    headers={"User-Agent": _pick_user_agent()},
                )
                resp.raise_for_status()

                # Response size guard — check Content-Length before reading body
                content_length = resp.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > _MAX_RESPONSE_SIZE_BYTES:
                            return "", (
                                f"Response too large ({content_length} bytes) from {url}. "
                                f"Max allowed: {_MAX_RESPONSE_SIZE_BYTES} bytes."
                            )
                    except ValueError:
                        pass  # Malformed content-length header; proceed cautiously

                # Content-type guard — reject obvious non-HTML binary types
                content_type = resp.headers.get("content-type", "").lower()
                if "application/pdf" in content_type:
                    return "", (
                        f"URL returned PDF content ({content_type}) from {url}. "
                        "Use file(action='read_pdf') or download to workspace/.artifacts/ instead."
                    )
                if "image/" in content_type:
                    return "", (
                        f"URL returned image content ({content_type}) from {url}. "
                        "Use browser(action='screenshot') for image extraction."
                    )
                # Allow text/html, application/xhtml+xml, text/plain, and
                # missing/unknown content-types (some servers omit the header).

                return resp.text, ""

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                # Exponential backoff: 1s, 2s, 4s, ... capped at 8s
                backoff = min(2 ** attempt, 8)
                time.sleep(backoff)
                continue
            return "", f"HTTP {status} from {url}"
        except _RETRYABLE_EXCEPTIONS:
            if attempt < _MAX_RETRIES:
                backoff = min(2 ** attempt, 8)
                time.sleep(backoff)
                continue
            return "", f"Network error fetching {url}"
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            return "", f"{type(e).__name__}: {e}"

    # Should never reach here — every loop path returns or continues.
    return "", f"Failed to fetch {url} after {_MAX_RETRIES + 1} attempts"


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
