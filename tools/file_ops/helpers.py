"""Path safety and resolution helpers for file operations.

Thin wrapper around core.path_guard. DO NOT implement custom path resolution here.

INTEGRATION GUIDE for future tool refactors:
  This module is the canonical example of how to wrap core.path_guard for a tool.
  It re-exports path_guard functions under the same names file action handlers expect,
  so handlers need zero changes when switching from custom logic to centralized guards.

  Old pattern (BUG — do not repeat):
    def _resolve(path_str):          # Custom logic, diverged from path_guard
        for root in _allowed_roots():  # Parallel security model
            ...

  New pattern (CORRECT):
    def _safe_resolve(path_str):     # Thin wrapper calling resolve_path()
        resolved, err = resolve_path(path_str, ...)
        ...
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.path_guard import resolve_path, check_protected_file


def _safe_resolve(path_str: str, require_exists: bool = False) -> tuple[Optional[Path], str]:
    """
    Safely resolve a path string using core.path_guard.resolve_path.

    This is the single entry point for all file action handlers to resolve paths.
    It delegates to the centralized path_guard so there is ONE source of truth
    for path validation, symlink safety, and root scoping.

    Args:
        path_str: The raw path string from the tool parameter.
        require_exists: If True, fail if the resolved path does not exist.

    Returns:
        (resolved_path, error_message)
        resolved_path is None on failure; error_message is "" on success.
    """
    if not path_str:
        return None, "path is required"

    resolved, err = resolve_path(path_str, default_root="agent", require_exists=require_exists)
    if not resolved:
        return None, err

    return resolved, ""
