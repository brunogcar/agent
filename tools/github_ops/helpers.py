"""tools/github_ops/helpers.py — Shared helpers for github API actions.

v1.4 (2026-07-15): core/net adoption. Provides three reusable helpers:
  - _check_configured(): eliminates the duplicated is_configured() guard
  - _coerce_int(): eliminates the duplicated int coercion (8 actions)
  - github_request(): wraps httpx call in core.net.retry.retry_sync with
    structured error_code from core.net.errors.classify_http_error

This module is the foundation for refactoring all 14 API actions to a
shared request path. The actions themselves still use the inline 3-stage
pattern (network → HTTP → JSON parse) in this commit — they'll be migrated
to github_request() in a follow-up commit. New actions written from scratch
SHOULD use github_request() directly.

== fail() contract (v1.4) ==
All fail() calls in this module use the default status="error" — NOT an int
status code. The status param on fail() expects a string (one of: "error",
"routed", "needs_clarification", etc.) — see core/contracts.py ToolResult.
Passing status=404 (an int) was a v1.3.1 contract violation that silently
broke `result["status"] == "error"` checks downstream. Structured error
classification now goes in error_code (TIMEOUT, RATE_LIMITED, SERVER_ERROR,
CLIENT_ERROR, NOT_FOUND, NETWORK_ERROR, CONNECT_ERROR, BOT_BLOCKED, UNKNOWN).

== Test patching note ==
helpers.py imports `get_client` by name from tools.github_ops.client — same
direct-reference pattern as the action modules. To test github_request()
directly, patch `tools.github_ops.helpers.get_client` (NOT the source
attribute at client.get_client — that won't intercept the local reference).
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import httpx

from core.contracts import fail
from core.net import retry_sync, classify_http_error, GITHUB_TIMEOUT
from tools.github_ops.client import get_client, is_configured


# Retry tuning for github_request — single API call, not a search.
# max_retries=2 means: initial attempt + 2 retries = 3 total attempts.
# base_delay=1.0s + jitter → ~1s, ~2s backoff. Capped at 5.0s.
# Tighter than the project-wide RETRY_BASE_DELAY=2.0 / RETRY_MAX_DELAY=30.0
# because GitHub API calls are user-facing and we don't want long stalls.
_GITHUB_MAX_RETRIES: int = 2
_GITHUB_BASE_DELAY: float = 1.0
_GITHUB_MAX_DELAY: float = 5.0


def _check_configured(trace_id: str = "") -> Optional[dict]:
    """Return fail() dict if GitHub is not configured, else None.

    Eliminates the duplicated guard at the top of every API action:
        if not is_configured():
            return fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env", trace_id=trace_id)

    Usage:
        err = _check_configured(trace_id)
        if err:
            return err
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )
    return None


def _coerce_int(
    value: Any, name: str, trace_id: str = ""
) -> Tuple[Optional[int], Optional[dict]]:
    """Coerce a value to int, returning (int_value, None) or (None, fail_dict).

    Eliminates the duplicated try/except int() coercion in 8 actions:
        try:
            n = int(number)
        except (TypeError, ValueError):
            return fail(f"number must be an int — got {number!r}", trace_id=trace_id)

    Usage:
        n, err = _coerce_int(number, "number", trace_id)
        if err:
            return err
    """
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, fail(f"{name} must be an int — got {value!r}", trace_id=trace_id)


def _do_request(
    client: httpx.Client,
    method: str,
    url_path: str,
    *,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
) -> httpx.Response:
    """Issue a single httpx request, raising on HTTP error so retry_sync sees it.

    Raises httpx.HTTPStatusError if status >= 400 — this lets retry_sync
    classify and retry the request based on the status code (via
    core.net.errors.is_retryable_error, which checks e.status_code against
    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}).
    """
    method_l = method.lower()
    if method_l == "get":
        resp = client.get(url_path, params=params, timeout=GITHUB_TIMEOUT)
    elif method_l == "post":
        resp = client.post(url_path, json=json, params=params, timeout=GITHUB_TIMEOUT)
    elif method_l == "put":
        resp = client.put(url_path, json=json, params=params, timeout=GITHUB_TIMEOUT)
    elif method_l == "patch":
        resp = client.patch(url_path, json=json, params=params, timeout=GITHUB_TIMEOUT)
    elif method_l == "delete":
        resp = client.delete(url_path, params=params, timeout=GITHUB_TIMEOUT)
    else:
        raise ValueError(f"unsupported HTTP method: {method!r}")

    # Raise on HTTP error so retry_sync can classify + retry based on status code.
    if resp.status_code >= 400:
        resp.raise_for_status()
    return resp


def github_request(
    method: str,
    url_path: str,
    trace_id: str = "",
    *,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
    not_found_msg: Optional[str] = None,
) -> Tuple[Optional[httpx.Response], Optional[dict]]:
    """Execute a GitHub API request with retry + structured error classification.

    Wraps the httpx call in core.net.retry.retry_sync (max_retries=2,
    base_delay=1.0, max_delay=5.0) so transient network errors and
    5xx/429 responses are retried with exponential backoff + jitter.

    On failure, returns (None, fail_dict) where fail_dict carries:
      - error_code from core.net.errors.classify_http_error (TIMEOUT,
        RATE_LIMITED, SERVER_ERROR, CLIENT_ERROR, NETWORK_ERROR,
        CONNECT_ERROR, BOT_BLOCKED, UNKNOWN)
      - NOT_FOUND mapped specially when not_found_msg is provided (404 only)
      - rate_limit_remaining in the fail dict when the
        X-RateLimit-Remaining response header is present
      - status defaults to "error" (NEVER an int — see fail() contract above)

    On success, returns (resp, None). The caller parses resp.json() and
    builds the ok() payload.

    Args:
        method: HTTP method ("get", "post", "put", "patch", "delete").
        url_path: Path under base URL (use repo_path() for repo-scoped calls).
        trace_id: Trace ID forwarded to fail().
        params: Optional query params (e.g. {"per_page": 100, "page": 2}).
        json: Optional JSON body for POST/PUT/PATCH.
        not_found_msg: Custom message for 404 responses. If None, the
            generic "GitHub API error 404: ..." message is used.

    Returns:
        (resp, None) on success.
        (None, fail_dict) on failure — caller returns fail_dict directly.

    Usage (in a future action refactor):
        resp, err = github_request(
            "get", f"{repo_path()}/pulls/{n}", trace_id,
            not_found_msg=f"PR #{n} not found",
        )
        if err:
            return err
        data = resp.json()
        return ok({...}, trace_id=trace_id)
    """
    client = get_client()
    try:
        resp = retry_sync(
            lambda: _do_request(client, method, url_path, params=params, json=json),
            max_retries=_GITHUB_MAX_RETRIES,
            base_delay=_GITHUB_BASE_DELAY,
            max_delay=_GITHUB_MAX_DELAY,
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_code = classify_http_error(e)

        # 404 special-case — many actions need a friendly "not found" message
        # (e.g. "PR #42 not found"). Fall through to the generic branch when
        # not_found_msg is None so callers see the raw GitHub message.
        if status_code == 404 and not_found_msg is not None:
            meta: dict = {}
            remaining = e.response.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                meta["rate_limit_remaining"] = remaining
            return None, fail(
                not_found_msg,
                trace_id=trace_id,
                error_code="NOT_FOUND",
                **meta,
            )

        # Try to extract GitHub's `message` field for a useful error string.
        try:
            err_body = e.response.json()
            gh_msg = err_body.get("message", e.response.text)
        except Exception:
            gh_msg = e.response.text or "<no body>"

        msg = f"GitHub API error {status_code}: {gh_msg}"
        meta = {}
        remaining = e.response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            meta["rate_limit_remaining"] = remaining
        return None, fail(
            msg, trace_id=trace_id, error_code=error_code, **meta
        )
    except Exception as e:
        # Network / timeout / unknown — classify_http_error still gives us a code.
        error_code = classify_http_error(e)
        return None, fail(
            f"GitHub request failed: {e}",
            trace_id=trace_id,
            error_code=error_code,
        )

    return resp, None
