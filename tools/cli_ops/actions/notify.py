"""
notify.py — Notification proxy for cli meta-tool.

Lazy imports notify tool.
"""

from __future__ import annotations

from typing import Any

def _notify(message: str) -> str:
    """Proxy to tools/notify.py."""
    from tools.notify import notify

    r = notify(action="send", message=message)
    if not isinstance(r, dict):
        return str(r)
    return r.get("message", str(r))