"""Web action: scrape — Fetch a URL and return clean extracted text.

Includes _fetch_html() and _html_to_text() helpers. These are private to
this module; other actions that need scraping should call _action_scrape().

[core/net adoption] Now uses retry_sync() from core/net/retry.py for unified
retry behavior. Hardcoded constants replaced with core/net/default.py imports.
Error classification uses is_retryable_error() from core/net/errors.py.

[v1.4] Error responses now include structured error_code from
classify_http_error() — was: raw "HTTP {status_code}" strings only.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

from core.config import cfg
from core.contracts import fail, ok
from core.net.retry import retry_sync
from core.net.errors import is_retryable_error, get_retry_delay, classify_http_error
from core.net.default import SCRAPE_TIMEOUT, SCRAPE_MAX_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY
from tools.web_ops._registry import register_action
from tools.web_ops.client import _make_client, _pick_user_agent
from tools.web_ops.utils import _is_safe_url

# Hard ceiling: reject responses larger than 10 MB before reading body.
_MAX_RESPONSE_SIZE_BYTES = 10 * 1024 * 1024


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
        # [v1.4] Surface structured error_code so callers can branch on
        # RATE_LIMITED / SERVER_ERROR / CLIENT_ERROR / etc. instead of
        # string-matching the error message.
        return fail(err, url=url, error_code=_scrape_error_code(err))

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


def _do_fetch(url: str, timeout: int) -> httpx.Response:
    """Single HTTP GET attempt. Raises on error — retry_sync handles retries.

    [core/net adoption] This is the function that retry_sync() wraps.
    Only the HTTP fetch is inside the retry boundary. Response validation
    (size, content-type) happens AFTER retry succeeds, in _fetch_html().
    """
    with _make_client() as client:
        resp = client.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _pick_user_agent()},
        )
        resp.raise_for_status()
        return resp


def _fetch_html(url: str, timeout: int = SCRAPE_TIMEOUT) -> tuple[str, str]:
    """Fetch URL using the pooled singleton client, return (html, error).

    Applies SSRF guard, response-size guard, content-type guard, and
    unified retry via retry_sync() on transient errors.
    Per-request User-Agent rotation to reduce 403 blocks.

    [core/net adoption] Replaced hand-rolled retry loop with retry_sync()
    from core/net/retry.py. Uses is_retryable_error() for classification
    and get_retry_delay() for backoff. Constants from core/net/default.py.
    """
    if not _is_safe_url(url):
        return "", f"Blocked for security: {url} resolves to a private/internal address"

    # Pre-flight PDF detection by URL extension
    if url.lower().rstrip("/").endswith(".pdf"):
        return "", (
            f"URL appears to be a PDF: {url}. "
            "Use file(action='read_pdf') or download to workspace/.artifacts/ instead."
        )

    # [core/net adoption] Use retry_sync() from core/net/retry.py.
    # max_retries and delays come from core/net/default.py.
    # is_retryable_error() classifies httpx errors and HTTP status codes.
    try:
        resp = retry_sync(
            lambda: _do_fetch(url, timeout),
            max_retries=SCRAPE_MAX_RETRIES,
            base_delay=RETRY_BASE_DELAY,
            max_delay=RETRY_MAX_DELAY,
            jitter=True,
            is_retryable=is_retryable_error,
        )
    except httpx.HTTPStatusError as e:
        # [v1.4] classify_http_error returns a structured code (RATE_LIMITED,
        # SERVER_ERROR, CLIENT_ERROR, etc.) so callers can branch on it.
        error_code = classify_http_error(e)
        return "", f"HTTP {e.response.status_code} from {url} [{error_code}]"
    except Exception as e:
        error_code = classify_http_error(e)
        return "", f"{type(e).__name__}: {e} [{error_code}]"

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


def _scrape_error_code(err: str) -> str:
    """[v1.4] Extract the error_code from the error string.

    _fetch_html() embeds the code in square brackets at the end of the
    message (e.g. "HTTP 503 from https://... [RATE_LIMITED]"). This helper
    extracts it so _action_scrape() can pass it to fail(error_code=...).
    Falls back to "UNKNOWN" if no bracketed code is found.
    """
    if "[" in err and err.endswith("]"):
        return err[err.rfind("[") + 1:-1]
    return "UNKNOWN"


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
