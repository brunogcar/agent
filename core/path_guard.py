"""core/path_guard.py — Centralized path validation and root scoping guards.

Security Model:
- AGENT_ROOT: Primary boundary (reads allowed, writes restricted)
- WORKSPACE_ROOT: Secondary boundary (subset of AGENT_ROOT, full access)
- Protected files: Read-allowed, write-blocked within AGENT_ROOT

All guards are O(1) and use pathlib.Path.resolve() for symlink safety.
Cross-platform: Fully compatible with Windows (NTFS/Junctions) and Linux.

INTEGRATION GUIDE for future tool refactors:
  Every tool that touches the filesystem MUST go through this module.
  The file and git refactors are the reference implementation.

  Three-layer defense pattern:
    1. Facade (tools/<tool>.py)     -> resolve_path() + check_protected_file()
    2. Helpers (tools/<tool>_ops/helpers.py) -> thin wrapper re-exporting path_guard
    3. Handlers (tools/<tool>_ops/actions/*.py) -> trust paths are validated; do NOT re-validate

  Anti-pattern: NEVER implement custom path resolution in helpers or handlers.
  The old file_ops refactor had _resolve() and _safe_resolve() in helpers.py
  that duplicated path_guard logic. That was a bug. Do not repeat it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from core.config import cfg
from core.tracer import tracer
from core.contracts import fail

# ── Constants ─────────────────────────────────────────────────────────────────
# READ_OPERATIONS: actions that only read — always allowed even on protected files.
# WRITE_OPERATIONS: actions that modify — blocked on protected files.
# When adding new file actions, UPDATE these sets or protected checks will silently fail.
# v1.1: Added move_file, copy_file, create_directory to WRITE_OPERATIONS (was missing).

READ_OPERATIONS = frozenset({
    "read", "list", "search", "read_pdf", "read_docx", "read_xlsx", "read_pptx",
    "exists", "stat", "head", "tail", "grep",
    "read_file", "list_directory", "search_files", "read_media_file",
    "directory_tree", "get_file_info", "find_files", "read_multiple_files",
    "list_allowed_directories",  # v1.1: added missing read action
})

WRITE_OPERATIONS = frozenset({
    "write", "edit", "delete", "backup", "patch", "append",
    "write_pdf", "write_docx", "write_xlsx", "write_pptx", "mkdir",
    "write_file", "edit_file", "delete_file", "patch_file", "append_file",
    "move_file", "copy_file", "create_directory",  # v1.1: added missing write actions
})

# v1.1: Added "clone" to GIT_WORKSPACE_ONLY since clone action is now implemented.
# Both "init" and "clone" require workspace scoping.
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

    Security properties:
      - Null bytes are blocked before any path parsing.
      - Symlinks are followed via Path.resolve() — symlink escapes are caught
        by the _is_within() check after resolution.
      - Absolute paths are allowed only if they resolve inside AGENT_ROOT.
      - Relative paths are resolved from default_root (agent or workspace).
    """
    if not path:
        return None, "Path cannot be empty"

    try:
        # Normalize slashes for cross-platform consistency
        p = Path(str(path).replace("\\", "/"))
    except Exception as e:
        return None, f"Invalid path format: {e}"

    # Explicit null byte check — defense in depth
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

    Returns True if child == parent or child is a descendant of parent.
    Returns False on any resolution error (e.g., broken symlink, permission denied).
    """
    try:
        child = child.resolve()
        parent = parent.resolve()
        return parent == child or parent in child.parents
    except (OSError, ValueError):
        return False

# ── Protected Files Guard ─────────────────────────────────────────────────────

def check_protected_file(path: str | Path, operation: str) -> Tuple[bool, str]:
    """
    Check if an operation is allowed on a potentially protected file.

    Read operations are ALWAYS allowed on protected files.
    Write operations are BLOCKED on protected files (as determined by cfg.is_protected).

    Args:
        path: The resolved Path to check (should already be validated by resolve_path).
        operation: The action name (e.g., "write_file", "read_file", "move_file").

    Returns:
        (allowed: bool, error_message: str)
        error_message is "" on success.
    """
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
        # File is not protected — write allowed
        return True, ""

    # Unknown operation: deny by default (fail-closed).
    # [Bug #2] Previously this returned True (allow) for unrecognized actions,
    # which meant a new write action added to a tool but forgotten in
    # WRITE_OPERATIONS would silently bypass protection on protected files.
    # Fail-closed is safer: new actions must be explicitly added to
    # READ_OPERATIONS or WRITE_OPERATIONS to be allowed on protected files.
    return False, (
        f"Operation '{operation}' is not in READ_OPERATIONS or WRITE_OPERATIONS. "
        f"Add it to core/path_guard.py to allow it on protected files."
    )

# ── Git Scoping Guard ─────────────────────────────────────────────────────────

def check_git_operation(
    operation: str,
    cwd: Optional[str | Path] = None,
    target: Optional[str | Path] = None,
) -> Tuple[bool, str, Optional[Path]]:
    """
    Validate git operation against scoping rules.

    Rules:
      - All git operations must be within AGENT_ROOT.
      - "init" and "clone" must be within WORKSPACE_ROOT.
      - For clone: the DESTINATION directory (derived from path parameter in handler)
        must be within WORKSPACE_ROOT. The target parameter is the remote URL and
        is NOT validated as a filesystem path.

    v1.1 fix: Added explicit existence check for cwd. Removed target validation for clone
    since target is a remote URL, not a local filesystem path.

    Args:
        operation: Git action name (e.g., "init", "commit", "clone").
        cwd: Working directory for the git command.
        target: Optional target — for clone this is a remote URL, NOT a filesystem path.

    Returns:
        (allowed: bool, error_message: str, resolved_cwd: Optional[Path])
    """
    if cwd:
        resolved_cwd, err = resolve_path(cwd, default_root="agent", require_exists=False)
        if not resolved_cwd:
            return False, err, None
        # v1.1: Explicit existence check. Git operations need a real directory.
        if not resolved_cwd.exists():
            return False, f"Working directory does not exist: {cwd}", None
        if not resolved_cwd.is_dir():
            return False, f"Not a directory: {cwd}", None
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

    # v1.1: Removed target validation for clone. Target is a remote URL, not a local path.
    # The handler validates the derived local destination path.

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
