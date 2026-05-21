"""
git.py — Git tool proxy for cli meta-tool.

Lazy imports git tool and normalizes dict output to human-readable strings.
"""

from __future__ import annotations

import json
from typing import Any

def _git(operation: str, **kw: Any) -> str:
    """Proxy to tools/git.py with formatted output."""
    from tools.git import git

    r = git(operation=operation, **kw)
    if not isinstance(r, dict):
        return str(r)

    if operation == "log":
        cs = r.get("commits", [])
        return "\n".join(
            f"{c.get('hash','')[:7]}  {c.get('message','').splitlines()[0][:70]}"
            for c in cs[:10]
        ) or "No commits."

    if operation == "diff":
        return r.get("diff", str(r))

    if r.get("status") == "error":
        return f"Error: {r.get('error', r)}"

    return r.get("message", json.dumps(r))