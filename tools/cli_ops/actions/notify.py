"""Notification proxy for cli meta-tool.

Lazy imports notify tool.
All functions auto-register via @register_action decorator.
"""
from __future__ import annotations

from typing import Any

from tools.cli_ops._registry import register_action


@register_action(
    "notify", "send",
    help_text="Send a notification (shortcut: 'notify <message>').",
    examples=["notify hello", "alert warning", "ping test"],
)
def _notify(action: str = "", message: str = "", **params) -> str:
    """Proxy to tools/notify.py."""
    from tools.notify import notify

    r = notify(action="send", message=message)
    if not isinstance(r, dict):
        return str(r)
    return r.get("message", str(r))
