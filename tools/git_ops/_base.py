"""Registry and decorator for git operation handlers."""

from __future__ import annotations
from typing import Callable, Optional

REGISTRY: dict[str, dict] = {}


def register_git(
    name: str,
    help_text: str,
    needs_repo: bool = False,
    examples: Optional[list[str]] = None,
):
    """
    Register a git operation handler.

    Args:
        name:       operation string the LLM uses, e.g. "commit".
        help_text:  help block to be included in the tool's docstring.
        needs_repo: if True, the dispatcher calls _check_repo() before invoking.
        examples:   optional list of example strings (e.g. ["git(operation="show", message="HEAD")"]).
    """
    def decorator(func: Callable) -> Callable:
        REGISTRY[name] = {
            "func": func,
            "help": help_text,
            "needs_repo": needs_repo,
            "examples": examples or [],
        }
        return func
    return decorator