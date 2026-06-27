"""Auto-registration registry for agent actions.

This module defines the central DISPATCH dictionary that maps
(tool_name, action_name) pairs to their handler functions and metadata.

The @register_action decorator is used by individual action modules
to automatically register themselves in DISPATCH at import time.
This eliminates manual wiring in a central dispatcher, making the
system fully extensible: to add a new agent action, simply:
 1. Create a new file in tools/agent_core/actions/
 2. Define a handler decorated with @register_action("agent", "action_name")
 3. The action is immediately available via the agent() tool

Thread Safety:
 DISPATCH is populated at import time (single-threaded during module load).
 No locking is required for registration. Handlers should be thread-safe
 if called concurrently.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Global dispatch table: {"agent": {"dispatch": {"func": ..., "help": ..., "examples": [...]}}}
# Populated automatically via @register_action decorators at import time.
DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator to register an agent action handler function with metadata.

    Args:
        tool_name: Tool namespace. Always "agent" for agent actions.
        action_name: Action identifier exposed to the LLM (e.g., "dispatch", "metrics").
        help_text: Help block to be included in the tool's dynamic docstring.
        examples: List of example strings for LLM reference.

    Returns:
        The original function, unmodified, after registration.

    Raises:
        ValueError: If the action_name is already registered for the tool_name.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        # Guard against duplicate action names — silent overwrites hide bugs
        if action_name in DISPATCH[tool_name]:
            raise ValueError(
                f"Duplicate action registration: '{action_name}' already exists "
                f"in DISPATCH['{tool_name}']. Check for colliding action files."
            )
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "examples": examples or [],
        }
        return func
    return decorator
