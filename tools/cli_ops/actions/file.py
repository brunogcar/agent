"""
file.py — File tool proxy for cli meta-tool.

Lazy imports file tool and normalizes dict output to human-readable strings.
"""

from __future__ import annotations

import json
from typing import Any

def _file(action: str, **kw: Any) -> str:
    """Proxy to tools/file.py with formatted output."""
    from tools.file import file

    r = file(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "read" and "content" in r:
        lines = r["content"].splitlines()
        out = "\n".join(f"{i+1:4d} | {l}" for i, l in enumerate(lines[:40]))
        if len(lines) > 40:
            out += f"\n... ({len(lines)-40} more lines)"
        return out

    if r.get("status") == "error":
        return f"Error: {r.get('error', r)}"

    return r.get("message", json.dumps(r, indent=2))