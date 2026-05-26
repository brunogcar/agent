"""
Auto-registration registry for git actions.

This module defines the central DISPATCH dictionary that maps
(tool_name, action_name) pairs to their handler functions and metadata.

The @register_action decorator is used by individual action modules
to automatically register themselves in DISPATCH at import time.
This eliminates manual wiring in a central dispatcher, making the
system fully extensible: to add a new git action, simply:
  1. Create a new file in tools/git_ops/actions/
  2. Define a handler decorated with @register_action("git", "action_name")
  3. The action is immediately available via the git() tool

Thread Safety:
    DISPATCH is populated at import time (single-threaded during module load).
    No locking is required for registration. Handlers should be thread-safe
    if called concurrently.
"""
from typing import Any, Callable, Dict, List, Optional

# Global dispatch table: {"git": {"status": {"func": ..., "help": ..., "needs_repo": ..., "examples": [...]}}}
# Populated automatically via @register_action decorators at import time.
DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    needs_repo: bool = False,
    examples: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator to register a git action handler function with metadata in the global DISPATCH table.

    Args:
        tool_name (str): Tool namespace. Always "git" for git actions.
        action_name (str): Action identifier exposed to the LLM (e.g., "status", "log").
        help_text (str): Help block to be included in the tool's dynamic docstring.
        needs_repo (bool): If True, the dispatcher calls _check_repo() before invoking the handler.
        examples (list[str], optional): List of example strings for LLM reference.

    Returns:
        Callable: The original function, unmodified, after registration.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "needs_repo": needs_repo,
            "examples": examples or [],
        }
        return func
    return decorator