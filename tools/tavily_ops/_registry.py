from __future__ import annotations
from typing import Any, Callable

DISPATCH: dict[str, dict[str, dict[str, Any]]] = {}


def register_action(tool_name: str, action_name: str, help_text: str = "",
                     examples: list[str] | None = None):
    def decorator(func: Callable) -> Callable:
        DISPATCH.setdefault(tool_name, {})
        if action_name in DISPATCH[tool_name]:
            raise ValueError(
                f"Duplicate action '{action_name}' for tool '{tool_name}' — "
                f"already registered by {DISPATCH[tool_name][action_name]['func'].__module__}"
            )
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "examples": examples or [],
        }
        return func
    return decorator
