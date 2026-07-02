"""Auto-registration registry for memory actions."""
from __future__ import annotations
from typing import Any, Callable

DISPATCH: dict[str, dict[str, dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: list[str] | None = None,
):
    """Decorator to register a memory action handler in the global DISPATCH table.

    Args:
        tool_name: Tool namespace. Always "memory" for memory actions.
        action_name: Action identifier exposed to the LLM.
        help_text: Help block included in the tool's dynamic docstring.
        examples: List of example strings for LLM reference.
    """

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
