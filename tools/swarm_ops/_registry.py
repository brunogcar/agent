"""Action registry for swarm_ops auto-discovery."""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}

def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: Optional[List[str]] = None,
) -> Callable:
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
