"""Auto-registration for file operations."""

from typing import Any, Callable

DISPATCH: dict[str, dict[str, Callable[..., Any]]] = {}

def register_action(tool_name: str, action_name: str):
    """Decorator to register action functions in DISPATCH."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        DISPATCH[tool_name][action_name] = func
        return func
    return decorator