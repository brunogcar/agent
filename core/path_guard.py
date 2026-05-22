"""
core/path_guard.py — Centralized path validation and root scoping guards.

Security Model:
  - AGENT_ROOT: Primary boundary (reads allowed, writes restricted)
  - WORKSPACE_ROOT: Secondary boundary (subset of AGENT_ROOT, full access)
  - Protected files: Read-allowed, write-blocked within AGENT_ROOT

All guards are O(1) and use pathlib.Path.resolve() for symlink safety.
Cross-platform: Fully compatible with Windows (NTFS/Junctions) and Linux.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from core.config import cfg
from core.tracer import tracer

# ── Constants ─────────────────────────────────────────────────────────────────
READ_OPERATIONS = frozenset({
    "read", "list", "search", "read_pdf", "read_docx", "read_xlsx", "read_pptx",
    "exists", "stat", "head", "tail", "grep"
})

WRITE_OPERATIONS = frozenset({
    "write", "edit", "delete", "backup", "patch", "append",
    "write_pdf", "write_docx", "write_xlsx", "write_pptx", "mkdir"
})

GIT_WORKSPACE_ONLY = frozenset({"clone", "init"})

# ── Path Resolution ───────────────────────────────────────────────────────────

def resolve_path(
    path: str | Path,
    default_root: str = "agent",
    require_exists: bool = False,
) -> Tuple[Optional[Path], str]:
    """
    Resolve a path against the appropriate root.
    Returns: (resolved_path, error_message)
    """
    if not path:
        return None, "Path cannot be empty"

    try:
        # Normalize slashes for cross-platform consistency
        p = Path(str(path).replace("\\", "/"))
    except Exception as e:
        return None, f"Invalid path format: {e}"

    # Explicit null byte check
    if "\x00" in str(path):
        return None, "Path contains null bytes"

    root = cfg.workspace_root.resolve() if default_root == "workspace" else cfg.agent_root.resolve()

    try:
        if p.is_absolute():
            resolved = p.resolve()
            if not _is_within(resolved, cfg.agent_root.resolve()):
                return None, (
                    f"Path '{path}' resolves outside AGENT_ROOT '{cfg.agent_root}'. "
                    f"Use paths relative to the project or workspace."
                )
        else:
            resolved = (root / p).resolve()
            if not _is_within(resolved, cfg.agent_root.resolve()):
                return None, f"Relative path '{path}' resolves outside AGENT_ROOT."
    except (OSError, ValueError) as e:
        # Catches null bytes and other OS-level path resolution errors
        return None, f"Invalid path or null bytes: {e}"

    if require_exists and not resolved.exists():
        return None, f"Path does not exist: {resolved}"

    return resolved, ""

def _is_within(child: Path, parent: Path) -> bool:
    """
    Check if child path is within parent path.
    Uses Path.resolve() to follow symlinks, ensuring symlink escapes are caught.
    """
    try:
        child = child.resolve()
        parent = parent.resolve()
        return parent == child or parent in child.parents
    except (OSError, ValueError):
        return False

# ── Protected Files Guard ─────────────────────────────────────────────────────

def check_protected_file(path: str | Path, operation: str) -> Tuple[bool, str]:
    """Read operations are ALWAYS allowed. Write operations are blocked on protected files."""
    resolved, err = resolve_path(path, default_root="agent", require_exists=False)
    if not resolved:
        return False, err

    if operation in READ_OPERATIONS:
        return True, ""

    if operation in WRITE_OPERATIONS:
        if hasattr(cfg, 'is_protected') and cfg.is_protected(resolved):
            return False, (
                f"Write operation blocked: '{path}' is a protected infrastructure file. "
                f"Reads are allowed, but modifications are forbidden."
            )
            
    return True, ""

# ── Git Scoping Guard ─────────────────────────────────────────────────────────

def check_git_operation(
    operation: str,
    cwd: Optional[str | Path] = None,
    target: Optional[str | Path] = None,
) -> Tuple[bool, str, Optional[Path]]:
    """Validate git operation against scoping rules."""
    if cwd:
        resolved_cwd, err = resolve_path(cwd, default_root="agent", require_exists=True)
        if not resolved_cwd:
            resolved_cwd, err = resolve_path(cwd, default_root="agent", require_exists=False)
            if not resolved_cwd:
                return False, err, None
    else:
        resolved_cwd = cfg.agent_root.resolve()

    if not _is_within(resolved_cwd, cfg.agent_root.resolve()):
        return False, f"Working directory '{cwd}' is outside AGENT_ROOT.", None

    if operation in GIT_WORKSPACE_ONLY:
        if not _is_within(resolved_cwd, cfg.workspace_root.resolve()):
            return False, (
                f"Operation '{operation}' must be performed within WORKSPACE_ROOT "
                f"'{cfg.workspace_root}', not '{resolved_cwd}'."
            ), None

        if target and operation == "clone":
            target_path, err = resolve_path(target, default_root="workspace", require_exists=False)
            if not target_path:
                return False, err, None
            if not _is_within(target_path, cfg.workspace_root.resolve()):
                return False, f"Clone target '{target}' must be within WORKSPACE_ROOT.", None

    return True, "", resolved_cwd

# ── Error Formatting ──────────────────────────────────────────────────────────

def make_path_error(path: str | Path, operation: str, reason: str, trace_id: str = "", suggestion: str = "") -> dict:
    """Create a standardized error response for path violations."""
    error_msg = f"Path guard blocked {operation} on '{path}': {reason}"
    if suggestion:
        error_msg += f" Suggestion: {suggestion}"
        
    return {
        "status": "error",
        "error": error_msg,
        "path": str(path),
        "operation": operation,
        "trace_id": trace_id or tracer.new_trace("path_guard", goal=f"{operation} {path}"),
    }