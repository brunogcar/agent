"""tools/vision_ops/helpers.py — Shared utilities for vision actions.

Extracted from the original 245-line tools/vision.py during the v1.0
@meta_tool refactor. These helpers are pure functions (with controlled
side effects: file reads, HTTP downloads, validation), so they can be
unit-tested in isolation by tests/tools/vision/test_helpers.py.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. HTTP_TIMEOUT / MAX_IMAGE_BYTES / MAX_BASE64_LEN are environment-
     configurable soft caps. The defaults (30s, 20MB, 10MB) match the
     Pre-v1 behavior and LM Studio's practical limits.
  2. _validate_vision_inputs() enforces "exactly one image source" — passing
     zero or multiple sources is a hard error. SSRF protection runs before
     any network call (DNS resolution happens inside is_safe_network_address).
  3. _file_to_block / _b64_to_block return (block_dict, error_str). The
     error_str is "" on success. The block_dict conforms to the OpenAI
     image_url content block shape:
         {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<...>"}}
     LM Studio and OpenAI-compatible providers both accept this shape.
  4. _download_image_to_data_uri wraps httpx.Client.get() in retry_sync()
     from core/net/retry.py. Vision uses max_retries=2 (vs the web tool's
     3) because it's a single image fetch, not a search — fewer retries
     means faster failure when a URL is genuinely broken.
  5. _check_vision_available() returns (ok, error_dict). When ok=False the
     error_dict has status="disabled" — distinct from "error" so the
     router / caller can distinguish "feature turned off" from "LLM blew up".

[core/net adoption — v1.0]:
  - retry_sync() from core/net/retry.py replaces the hand-rolled try/except
    loop in the legacy _download_image_to_data_uri. is_retryable_error()
    from core/net/errors.py classifies httpx errors and HTTP status codes.
  - RETRY_BASE_DELAY and RETRY_MAX_DELAY come from core/net/default.py so
    the vision tool's backoff profile is centrally tunable alongside
    tavily_ops / web_ops / browser.
  - is_safe_network_address() from core/net/security.py provides SSRF
    protection (was already used in Pre-v1 — kept as-is).
"""
from __future__ import annotations

import base64 as _b64
import os
import sys
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse

import httpx

from core.config import cfg
from core.llm import llm
from core.net.errors import is_retryable_error
from core.net.retry import retry_sync
from core.net.security import is_safe_network_address
from core.net.default import RETRY_BASE_DELAY, RETRY_MAX_DELAY
from core.tracer import tracer

# ── Constants (env-configurable soft caps) ───────────────────────────────────
HTTP_TIMEOUT = 30.0  # seconds — single-image download timeout
MAX_IMAGE_BYTES = int(os.environ.get("VISION_MAX_FILE_BYTES", 20_000_000))
MAX_BASE64_LEN = int(os.environ.get("VISION_MAX_BASE64_LEN", 10_000_000))

# Vision uses fewer retries than the web tool (single image fetch, not a search).
# Local constant — kept here rather than in core/net/default.py because it's a
# vision-specific tuning value (web/scrape uses 3, browser nav uses 2, vision uses 2).
_VISION_DOWNLOAD_RETRIES = 2

# ── MIME map (file extension → content type) ─────────────────────────────────
_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
    ".gif": "image/gif",  ".bmp":  "image/bmp",
}


def _validate_vision_inputs(file_path: str, base64_str: str, url: str) -> Tuple[bool, str]:
    """Validate that exactly one image source is provided and run safety checks.

    Returns:
        (is_valid, error_message) — error_message is "" on success.

    Checks:
      - Exactly one of (file_path, base64_str, url) is non-empty.
      - URL: hostname resolves to a public IP (SSRF guard via
        is_safe_network_address). Scheme must be http or https.
      - file_path: exists, is a file, and is under MAX_IMAGE_BYTES.
      - base64_str: under MAX_BASE64_LEN chars.
    """
    sources = [s for s in [file_path, base64_str, url] if s and s.strip()]
    if len(sources) == 0:
        return False, "Exactly one image source (file_path, base64, or url) is required."
    if len(sources) > 1:
        return False, "Provide exactly ONE image source, not multiple."

    if url:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return False, "Invalid URL: missing hostname"

        # SSRF Protection: Network-scope blocking + allowlist
        if not is_safe_network_address(hostname):
            tracer.warning(
                "", "vision_ssrf", f"SSRF blocked: {url} → {hostname}",
                action="blocked", url=url, hostname=hostname, reason="private_network",
            )
            return False, f"SSRF blocked: {url} points to private/localhost network"

        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed."

    if file_path:
        p = Path(file_path)
        if not p.exists():
            return False, f"File not found: {file_path}"
        if not p.is_file():
            return False, f"Not a file: {file_path}"
        if p.stat().st_size > MAX_IMAGE_BYTES:
            return False, f"File too large ({p.stat().st_size} bytes, max {MAX_IMAGE_BYTES})."

    if base64_str:
        if len(base64_str) > MAX_BASE64_LEN:
            return False, f"Base64 string too long ({len(base64_str)} chars, max {MAX_BASE64_LEN})."

    return True, ""


def _file_to_block(file_path: str) -> Tuple[dict, str]:
    """Read a local image file and return an OpenAI image_url content block.

    Returns (block, error_str). error_str is "" on success.

    MIME is detected from the file extension via _MIME_MAP. Unknown
    extensions default to image/jpeg (with a stderr warning) — this matches
    LM Studio's behavior of tolerating slightly-wrong MIME types.
    """
    p = Path(file_path)
    mime = _MIME_MAP.get(p.suffix.lower(), "image/jpeg")
    if not _MIME_MAP.get(p.suffix.lower()):
        print(f"[vision] Unknown extension {p.suffix}, defaulting to image/jpeg", file=sys.stderr)

    try:
        data = _b64.b64encode(p.read_bytes()).decode("utf-8")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}, ""
    except Exception as e:
        return {}, f"Read error: {e}"


def _b64_to_block(b64_str: str, mime_type: str = "image/jpeg") -> Tuple[dict, str]:
    """Build an OpenAI image_url content block from a base64 string or data URI.

    Returns (block, error_str). error_str is always "" (this function never
    fails — bad inputs surface as a malformed data URI that the LLM provider
    will reject downstream).

    If b64_str already starts with "data:", it's passed through unchanged.
    Otherwise it's wrapped as data:<mime_type>;base64,<b64_str>.
    """
    if b64_str.startswith("data:"):
        return {"type": "image_url", "image_url": {"url": b64_str}}, ""
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_str}"}}, ""


def _do_download(url: str, timeout: float) -> httpx.Response:
    """Single HTTP GET attempt. Raises on error — retry_sync handles retries.

    [core/net adoption] This is the function that retry_sync() wraps.
    Only the HTTP fetch is inside the retry boundary. MIME detection and
    base64 encoding happen AFTER retry succeeds, in _download_image_to_data_uri.

    v1.4: Uses core/net/client.get_shared_client() instead of creating a
    fresh httpx.Client per call (was: `with httpx.Client(timeout=timeout) as client:`
    → created + destroyed a new connection pool per image download).
    """
    from core.net.client import get_shared_client
    client = get_shared_client()
    resp = client.get(url, follow_redirects=True, timeout=timeout)
    resp.raise_for_status()
    return resp


def _download_image_to_data_uri(url: str, timeout: float = HTTP_TIMEOUT) -> Tuple[str, str]:
    """Download an image from a URL and return a base64 data URI.

    Returns (data_uri, error_str) where error_str is "" on success.

    [core/net adoption] Replaced the hand-rolled try/except loop with
    retry_sync() from core/net/retry.py. Uses is_retryable_error() for
    classification and the central RETRY_BASE_DELAY / RETRY_MAX_DELAY
    constants from core/net/default.py. Vision uses max_retries=2 (one
    fewer than the web tool) — single image fetch, not a search.
    """
    try:
        resp = retry_sync(
            lambda: _do_download(url, timeout),
            max_retries=_VISION_DOWNLOAD_RETRIES,
            base_delay=RETRY_BASE_DELAY,
            max_delay=RETRY_MAX_DELAY,
            jitter=True,
            is_retryable=is_retryable_error,
        )
    except Exception as e:
        # Classify the final exception for a clean error message.
        if isinstance(e, httpx.TimeoutException):
            return "", f"Timeout downloading image from {url} (>{timeout}s)"
        elif isinstance(e, httpx.HTTPStatusError):
            return "", f"HTTP error {e.response.status_code} downloading image."
        else:
            return "", f"Download error: {e}"

    content_type = resp.headers.get("content-type", "image/jpeg")
    # Some servers send "image/png; charset=utf-8" — strip after the semicolon.
    content_type = content_type.split(";")[0].strip()
    if not content_type.startswith("image/"):
        suffix = Path(url.split("?")[0]).suffix.lower()
        content_type = _MIME_MAP.get(suffix, "image/jpeg")

    b64 = _b64.b64encode(resp.content).decode("utf-8")
    return f"data:{content_type};base64,{b64}", ""


def _check_vision_available() -> Tuple[bool, dict]:
    """Pre-flight check: is the vision role configured?

    Returns (ok=True, {}) when the vision model is configured.
    Returns (ok=False, error_dict) with status="disabled" when
    cfg.vision_model is empty (kill switch — feature turned off).

    Unlike consultor, the vision role routes through llm.call() (not
    llm.complete()) because it needs multimodal messages with image_url
    content blocks. We don't check llm.is_available('vision') here because
    the role may not be registered in model_registry — vision is typically
    configured via VISION_MODEL env var alone. The provider lookup happens
    inside llm.call() via role fallback to executor.
    """
    if not cfg.vision_model:
        return False, {
            "status": "disabled",
            "error": "VISION_MODEL not set in .env — add it to your .env file",
        }
    return True, {}


def _build_image_block(
    file_path: str, base64_str: str, url: str, mime_type: str,
) -> Tuple[dict, str]:
    """Build the image content block from whichever source was provided.

    Returns (block, error_str). error_str is "" on success.

    Centralizes the if/elif/elif dispatch over source type so action handlers
    don't duplicate the branching logic. Callers MUST have already validated
    inputs via _validate_vision_inputs() before calling this.
    """
    if file_path:
        return _file_to_block(file_path)
    if base64_str:
        return _b64_to_block(base64_str, mime_type)
    if url:
        data_uri, err = _download_image_to_data_uri(url)
        if err:
            return {}, err
        return _b64_to_block(data_uri, mime_type)
    # Should be unreachable if _validate_vision_inputs was called first.
    return {}, "No image source provided (validation skipped)."


def _call_vision(
    system: str,
    user_content: list,
    json_mode: bool = False,
    json_schema: str = "",
    trace_id: str = "",
):
    """Invoke llm.call(role='vision', ...) with multimodal messages.

    Centralizes LLM access so action handlers don't reference `llm` directly.
    Tests that patch `tools.vision_ops.helpers.llm` transparently intercept
    this call.

    Args:
        system: System prompt string.
        user_content: List of content blocks (text + image_url) for the user
                      message. Vision uses multimodal content, not the
                      plain-string `user` field that llm.complete() expects.
        json_mode: Forwarded to llm.call(). Enables JSON parsing in the
                   response (result.parsed).
        json_schema: JSON schema string for structured output. When non-empty,
                     parsed as a dict and forwarded as json_schema= to llm.call().
                     Per llm.call() semantics, providing a schema implies
                     json_mode for response parsing.
        trace_id: Observability threading ID.

    Returns:
        The LLMResponse object from llm.call() (real or mocked).
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    schema_dict = None
    if json_schema and json_schema.strip():
        try:
            import json as _json
            schema_dict = _json.loads(json_schema)
        except Exception:
            # Malformed schema string — let llm.call() proceed without it.
            # The LLM will produce unstructured output; the caller can detect
            # this via result.parsed being None.
            schema_dict = None

    return llm.call(
        role="vision",
        messages=messages,
        json_mode=json_mode,
        json_schema=schema_dict,
        trace_id=trace_id,
    )
