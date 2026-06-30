"""Web action: read — Alias for scrape with prune_tool_dict applied.

This is the primary user-facing action for reading a single web page.
It returns pruned output (truncated + artifact-saved) to prevent
context window overflow on large pages.
"""
from __future__ import annotations

from typing import Optional

from tools.web_ops._registry import register_action
from tools.web_ops.actions.scrape import _action_scrape


@register_action(
    "web",
    "read",
    help_text="""read — Fetch a URL and return clean, pruned text content.
Required: url
Optional: max_chars (default from cfg.web_max_text_chars)
Note: This is the preferred action for reading web pages. Use 'scrape' only
      when you need the raw unpruned text.""",
    examples=[
        'web(action="read", url="https://docs.python.org/3/library/pathlib.html")',
    ],
)
def _action_read(
    url: str = "",
    max_chars: Optional[int] = None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Fetch URL and return pruned text (head+tail truncation + artifact storage).

    Calls _action_scrape internally, then pipes the result through
    prune_tool_dict() from core.memory_backend.pruner.
    """
    result = _action_scrape(url=url, max_chars=max_chars, trace_id=trace_id, **kwargs)
    if result.get("status") != "success":
        return result

    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("web", result, trace_id)
