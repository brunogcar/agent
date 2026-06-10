"""
git.py — Git tool proxy for cli meta-tool.

Lazy imports git tool and normalizes dict output to human-readable strings.
All functions auto-register via @register_action decorator.
"""

from __future__ import annotations

import json
from typing import Any

from tools.cli_ops._registry import register_action

@register_action("git", "status")
@register_action("git", "log")
@register_action("git", "diff")
@register_action("git", "snapshot")
@register_action("git", "commit")
@register_action("git", "rollback")
def _git(action: str, **kw: Any) -> str:
    """Proxy to tools/git.py with formatted output."""
    from tools.git import git

    r = git(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "log":
        cs = r.get("commits", [])
        return "\n".join(
            f"{c.get('hash','')[:7]}  {c.get('message','').splitlines()[0][:70]}"
            for c in cs[:10]
        ) or "No commits."

    if action == "diff":
        return r.get("diff", str(r))

    if r.get("status") == "error":
        return f"Error: {r.get('error', r)}"

    return r.get("message", json.dumps(r))