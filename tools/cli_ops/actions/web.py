"""
web.py — Web tool proxy for cli meta-tool.

Lazy imports web tool and normalizes dict output to human-readable strings.
"""

from __future__ import annotations

from typing import Any

def _web(action: str, **kw: Any) -> str:
    """Proxy to tools/web.py with formatted output."""
    from tools.web import web

    r = web(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "search":
        results = r.get("results", [])
        return "\n".join(
            f"{i+1}. {x.get('title','')}\n   {x.get('url','')}\n   {x.get('snippet','')[:100]}"
            for i, x in enumerate(results[:5])
        ) or "No results."

    if action in ("scrape", "read"):
        return r.get("text", str(r))[:3000]

    if r.get("status") == "error":
        return f"Error: {r.get('error', r)}"

    return str(r)