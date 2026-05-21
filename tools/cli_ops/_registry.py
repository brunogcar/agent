"""Action registry for cli_ops auto-discovery."""

from __future__ import annotations

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., object])

# Nested dict: tool_name -> action_name -> callable
DISPATCH: dict[str, dict[str, Callable]] = {}

def register_action(tool_name: str, action_name: str | None = None) -> Callable[[F], F]:
    """Decorator to register an action with the dispatch registry."""
    def decorator(func: F) -> F:
        nonlocal action_name  # ← Add this line
        if action_name is None:
            action_name = func.__name__
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        DISPATCH[tool_name][action_name] = func
        return func
    return decorator