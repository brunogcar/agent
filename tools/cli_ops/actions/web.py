"""Web tool proxy for cli meta-tool.

Lazy imports web tool and normalizes dict output to human-readable strings.
All functions auto-register via @register_action decorator.

NOTE: CLI uses stacked decorators on a single handler per tool namespace.
See actions/file.py for explanation.
"""
from __future__ import annotations

from typing import Any

from tools.cli_ops._registry import register_action


@register_action(
    "web", "search",
    help_text="Search the web (shortcut: 'search <query>').",
    examples=["search python tutorials"],
)
@register_action(
    "web", "scrape",
    help_text="Scrape a webpage (shortcut: 'scrape <url>').",
    examples=["scrape https://example.com"],
)
@register_action(
    "web", "read",
    help_text="Read a webpage (shortcut: 'read <url>').",
    examples=["read https://example.com"],
)
def _web(action: str = "", **kw: Any) -> str:
    """Proxy to tools/web.py with formatted output."""
    from tools.web import web

    r = web(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "search":
        results = r.get("results", [])
        lines = []
        for i, x in enumerate(results[:5]):
            title = x.get("title", "")
            url = x.get("url", "")
            snippet = x.get("snippet", "")[:100]
            lines.append(f"{i+1}. {title}\n   {url}\n   {snippet}")
        return "\n".join(lines) or "No results."

    if action in ("scrape", "read"):
        return r.get("text", str(r))[:3000]

    if r.get("status") == "error":
        err = r.get("error", r)
        return f"Error: {err}"

    return str(r)
