"""Action registry for cli_ops auto-discovery.

Stores metadata dict per action: {"func", "help", "examples"}.
Populated at import time via @register_action decorators.

Thread Safety:
  DISPATCH is populated at import time (single-threaded during module load).
  No locking is required for registration. Handlers should be thread-safe
  if called concurrently.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Global dispatch table: {"cli": {"health": {"func": ..., "help": ..., "examples": [...]}}}
# Populated automatically via @register_action decorators at import time.
DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: Optional[List[str]] = None,
) -> Callable:
    """Register a CLI proxy action handler with metadata.

    Args:
        tool_name: Tool namespace (e.g., "cli", "file", "git").
        action_name: Action identifier (e.g., "health", "read_file").
        help_text: One-line description for auto-generated docstrings.
        examples: List of example command strings for LLM reference.

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
