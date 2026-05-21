"""
notify.py — Notification proxy for cli meta-tool.

Lazy imports notify tool.
All functions auto-register via @register_action decorator.
"""

from __future__ import annotations

from typing import Any

from tools.cli_ops.actions._registry import register_action

@register_action("notify", "send")
def _notify(message: str = "") -> str:
    """Proxy to tools/notify.py."""
    from tools.notify import notify

    r = notify(action="send", message=message)
    if not isinstance(r, dict):
        return str(r)
    return r.get("message", str(r))