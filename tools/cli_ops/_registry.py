"""Action registry for cli_ops auto-discovery.

Stores metadata dict per action: {"func", "help", "examples"}.
Populated at import time via @register_action decorators.

Thread Safety:
  DISPATCH is populated at import time (single-threaded during module load).
  No locking is required for registration. Handlers should be thread-safe
  if called concurrently.

Collision Handling:
  If two @register_action decorators target the same `tool_name:action_name`
  pair, the second registration OVERWRITES the first (backward compat —
  patterns.py relies on later registrations winning to avoid name
  collisions like "read" between web and file). A warning is logged via
  the standard `logging` module so collisions are visible without breaking
  imports. We log (not print) because MCP stdio would be corrupted by
  print() output. We warn (not raise) because raising would break
  auto-discovery and prevent the agent from starting.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

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
        # Collision guard: warn (but still overwrite) if the same
        # tool_name:action_name is already registered. We warn instead of
        # raise because (a) backward compat — patterns.py relies on later
        # registrations winning (see the "MOVED BEFORE FILE to avoid 'read'
        # collision" comment in patterns.py), and (b) raising would break
        # auto-discovery and prevent the agent from starting. The warning
        # makes collisions visible in logs without breaking anything.
        if action_name in DISPATCH[tool_name]:
            existing = DISPATCH[tool_name][action_name]
            existing_func = existing.get("func", "")
            existing_loc = (
                f"{existing_func.__module__}.{existing_func.__name__}"
                if callable(existing_func)
                else "<unknown>"
            )
            new_loc = f"{func.__module__}.{func.__name__}"
            logger.warning(
                f"CLI dispatch collision: '{tool_name}:{action_name}' "
                f"already registered by {existing_loc}. "
                f"Overwriting with {new_loc}."
            )
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "examples": examples or [],
        }
        return func
    return decorator
