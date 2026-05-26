"""
Path safety and resolution helpers for file operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.config import cfg

# ── Path safety ───────────────────────────────────────────────────────────────

_ALLOWED_ROOTS = None

def _allowed_roots() -> list[Path]:
    global _ALLOWED_ROOTS
    if _ALLOWED_ROOTS is None:
        _ALLOWED_ROOTS = [
            cfg.agent_root.resolve(),
            cfg.workspace_root.resolve(),
        ]
    return _ALLOWED_ROOTS

def _resolve(path_str: str) -> Optional[Path]:
    """
    Resolve a path safely.
    - Absolute paths are used as-is (if within allowed roots)
    - Relative paths are resolved from agent_root FIRST, then workspace_root
    Returns None if the path escapes allowed roots.
    """
    # Defense-in-depth: Block null byte injection attacks
    if "\x00" in str(path_str):
        return None

    p = Path(path_str)

    # For relative paths: try agent_root first (source code lives here)
    if not p.is_absolute():
        for root in _allowed_roots():
            candidate = root / p
            if candidate.exists():
                resolved = candidate.resolve()
                try:
                    resolved.relative_to(root)
                    return resolved
                except ValueError:
                    continue
        # If not found in any root, try workspace_root as fallback
        candidate = cfg.workspace_root / p
        resolved = candidate.resolve()
        for root in _allowed_roots():
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        return None

    # For absolute paths
    resolved = p.resolve()
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None  # path escapes allowed roots

def _safe_resolve(path_str: str) -> tuple[Optional[Path], str]:
    """Returns (resolved_path, error_message). error is "" on success."""
    if not path_str:
        return None, "path is required"
    if "\x00" in str(path_str):
        return None, "Path contains invalid null bytes"
    p = _resolve(path_str)
    if p is None:
        return None, (
            f"Path '{path_str}' is outside allowed directories. "
            f"Use paths within agent ({cfg.agent_root}) or workspace ({cfg.workspace_root})."
        )
    return p, ""