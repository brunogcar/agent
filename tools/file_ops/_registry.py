"""Auto-registration for file operations."""

from typing import Any, Callable, Dict, List, Optional

# Global dispatch table: {"file": {"read_file": {"func": ..., "help": ..., "examples": [...]}}}
# Populated automatically via @register_action decorators at import time.
DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator to register a file action handler function with metadata.

    Args:
        tool_name: Tool namespace. Always "file" for file actions.
        action_name: Action identifier exposed to the LLM (e.g., "read_file").
        help_text: Help block to be included in the tool's dynamic docstring.
        examples: List of example strings for LLM reference.

    Returns:
        The original function, unmodified, after registration.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "examples": examples or [],
        }
        return func

    return decorator
