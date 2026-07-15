"""Action registry for schedule_ops auto-discovery.

Mirrors the pattern in notify_ops/_registry.py and consult_ops/_registry.py:
- DISPATCH is a nested dict keyed by tool_name -> action_name -> handler metadata.
- Each action module imports `register_action` and decorates its handler at
  module import time.
- The facade imports `from tools import schedule_ops` (which triggers
  __init__.py's auto-discovery) BEFORE reading DISPATCH, so the dispatch
  table is populated when @meta_tool runs.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. DISPATCH is module-level. All action modules share the same dict instance
     via the `from ... import DISPATCH` re-export pattern.
  2. Duplicate registration raises ValueError loudly — never silently
     overwrite. Catches accidental double-imports and copy-paste bugs.
  3. The `func` reference is the raw callable — not a partial or wrapper.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: Optional[List[str]] = None,
) -> Callable:
    """Decorator that registers a handler under DISPATCH[tool_name][action_name].

    Args:
        tool_name: Top-level tool key (e.g. "schedule").
        action_name: Action key (e.g. "add_cron", "list", "cancel").
                     Must match ^[a-z][a-z0-9_]*$ — enforced by @meta_tool.
        help_text: Human-readable description used in the generated docstring.
        examples: Optional list of call-example strings shown in the docstring.

    Returns:
        The original function unchanged (decorator is registration-only).
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        if action_name in DISPATCH[tool_name]:
            raise ValueError(
                f"Duplicate action registration: '{action_name}' already exists "
                f"in DISPATCH['{tool_name}']."
            )
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "examples": examples or [],
        }
        return func
    return decorator
