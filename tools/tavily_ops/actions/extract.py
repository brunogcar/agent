"""tools/tavily_ops/actions/extract.py — Tavily extract action handler.

v1.2: Consistency fix — use coroutine factory pattern even though extract
doesn't use _run_async_with_resilience (keyless mode uses plain _run_async).
v1.3 FIXES:
- Wire _run_async_with_resilience for CB + retry (was bypassing all resilience).
- Wire core/net/default constants.
- Wire budget tracking.
- Wire URL normalization for URL deduplication.
"""
from __future__ import annotations
from typing import Optional, List

from core.contracts import ok, fail
from core.net.budget import record_tool_call, check_budget
from core.net.default import EXTRACT_MAX_URLS, EXTRACT_DEPTH
from core.net.url import normalize_url
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.errors import _handle_tavily_error, _assert_safe_urls
import tools.tavily_ops.client as _client
from tools.tavily_ops import bridge

@register_action(
    "tavily", "extract",
    help_text="""extract — Bulk URL content extraction.
Required: urls (list, max 10)
Optional: include_images, extract_depth, format""",
    examples=[
        'tavily(action="extract", urls=["https://example.com"])',
        'tavily(action="extract", urls=["https://a.com", "https://b.com"], extract_depth="advanced")',
    ],
)
def _action_extract(
    urls: Optional[List[str]] = None,
    include_images: bool = False,
    extract_depth: str = EXTRACT_DEPTH,
    format: str = "markdown",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Execute Tavily extract and return pruned result.

    v1.3: Now uses _run_async_with_resilience for circuit breaker + retry.
    """
    if not urls:
        return fail("urls is required for extract action", trace_id=trace_id)
    if len(urls) > EXTRACT_MAX_URLS:
        return fail(f"urls cannot exceed {EXTRACT_MAX_URLS} items", trace_id=trace_id)

    # v1.3: Normalize URLs for deduplication and cache key consistency
    urls = [normalize_url(u) for u in urls]

    err = _assert_safe_urls(urls)
    if err:
        return fail(err, trace_id=trace_id)

    # v1.3: Budget check
    if not check_budget("tavily.extract"):
        return fail(
            "Tavily extract budget exhausted. Try again tomorrow.",
            trace_id=trace_id,
            error_code="QUOTA_EXHAUSTED",
        )

    keyless = _client._is_keyless()
    if keyless:
        _client._warn_keyless_once()

    def _call():
        client = _client._get_singleton_client()
        return client.extract(
            urls=urls,
            include_images=include_images,
            extract_depth=extract_depth,
            format=format,
        )

    try:
        # v1.3 FIX: Use _run_async_with_resilience instead of _run_async(_call())
        result = bridge._run_async_with_resilience(_call, trace_id=trace_id)
    except Exception as e:
        return _handle_tavily_error(e, trace_id=trace_id)

    # v1.3: Record successful API call
    record_tool_call("tavily.extract")

    response = ok(
        {"results": result.get("results", []), "keyless": keyless},
        trace_id=trace_id,
    )

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("tavily", response, trace_id)
