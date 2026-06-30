"""Tavily action: extract — Bulk URL content extraction."""
from __future__ import annotations
from typing import Optional

from core.contracts import ok, fail
from tools.tavily_ops._registry import register_action
from tools.tavily_ops.bridge import _run_async
import tools.tavily_ops.client as _client
from tools.tavily_ops.errors import _handle_tavily_error, _assert_safe_urls


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
    urls: Optional[list[str]] = None,
    include_images: bool = False,
    extract_depth: str = "basic",
    format: str = "markdown",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Execute Tavily extract and return pruned result."""
    if not urls:
        return fail("urls is required for extract action", trace_id=trace_id)
    if len(urls) > 10:
        return fail("urls cannot exceed 10 items", trace_id=trace_id)

    err = _assert_safe_urls(urls)
    if err:
        return fail(err, trace_id=trace_id)

    keyless = _client._is_keyless()
    if keyless:
        _client._warn_keyless_once()

    async def _call():
        client = _client._get_singleton_client()
        return await client.extract(
            urls=urls,
            include_images=include_images,
            extract_depth=extract_depth,
            format=format,
        )

    try:
        result = _run_async(_call())
    except Exception as e:
        return _handle_tavily_error(e)

    response = ok(
        {"results": result.get("results", []), "keyless": keyless},
        trace_id=trace_id,
    )

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("tavily", response, trace_id)
