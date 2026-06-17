"""Shared utilities and helpers for cli meta-tool operations.

Includes:
- Command sanitization and validation
- Workspace/cwd detection
- Secure shell execution wrapper (shell=False + allowlist)
- Safe dispatch to registered actions
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from core.config import cfg

# =============================================================================
# Constants
# =============================================================================
# [P2] Limits centralized in core/config.py

_CONTROL_CHAR_PATTERN = re.compile(r'[\x00--]')

# ── Security: Allowlist & Denylist ─────────────────────────────────────
# Base commands allowed for execution. shell=False prevents chaining.
ALLOWED_COMMANDS = frozenset({
    # File/Dir ops
    "ls", "dir", "cat", "type", "head", "tail", "grep", "findstr",
    "wc", "find", "cp", "copy", "mv", "move", "mkdir", "rmdir",
    "touch", "stat", "du", "df", "pwd", "cd",
    # Git & Dev
    "git", "gh", "python", "python3", "pip", "pytest",
    # Text/System
    "sed", "awk", "cut", "sort", "uniq", "tr", "tee",
    "uname", "whoami", "date", "echo", "which", "where",
    "systeminfo", "ipconfig", "hostname", "tasklist", "ver"
})

# Shell operators that are dangerous or useless with shell=False
SHELL_OPERATORS = {"|", "||", "&&", ";", ">", ">>", "<", "&", "`", "$("}

# [BUGFIX-3] Dangerous flags that enable arbitrary code execution even when
# the base command is allowlisted (e.g., "python -c 'import os; os.system(...)'").
# These flags are checked after normalization (handles --command=..., -cfile.py, etc.)
BLOCKED_FLAGS = frozenset({"-c", "-m", "--command", "--module", "-e", "--eval"})


def _normalize_flag(token: str) -> str | None:
    """Normalize a CLI token to its canonical flag form for blacklist checking.

    Handles:
      --command=value  → --command
      -cfile.py        → -c
      --co             → --co (argparse prefix, not matched unless in BLOCKED_FLAGS)
    """
    if not token.startswith("-"):
        return None
    # Handle --flag=value syntax: split on first '='
    if "=" in token:
        return token.split("=", 1)[0]
    # Handle combined short flags: -cm → -c (the first flag is the dangerous one)
    if len(token) > 2 and not token.startswith("--"):
        return token[:2]
    return token

# =============================================================================
# Sanitization
# =============================================================================
def _sanitize_command(command: str) -> str:
    """
    Sanitize command input before processing.
    """
    if not isinstance(command, str):
        raise ValueError("Command must be a string")

    # [P2] Use centralized config limit (4096 chars)
    if len(command) > cfg.cli_max_command_chars:
        raise ValueError(f"Command too long (max {cfg.cli_max_command_chars} chars)")

    if '\x00' in command:
        raise ValueError("Command contains null bytes")

    if _CONTROL_CHAR_PATTERN.search(command):
        raise ValueError("Command contains control characters")

    # Check for dangerous patterns (injection attempts)
    DANGEROUS_PATTERNS = ['rm -rf', 'passwd', 'hacked', 'root@', 'etc/passwd', 'chmod 777']
    command_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command_lower:
            raise ValueError("Command contains blocked pattern")

    command = ' '.join(command.split())

    args = command.split()
    # [P2] Use centralized config limit
    if len(args) > cfg.cli_max_arguments:
        raise ValueError("too many arguments")

    return command

# =============================================================================
# Workspace Detection
# =============================================================================
def _detect_cwd(command: str) -> Path | None:
    """Detect working directory from command."""
    command_lower = command.lower().strip()

    if command_lower.startswith("cd "):
        target = command[3:].strip()
        if target:
            try:
                return Path(target)
            except Exception:
                pass

    tokens = command.split()
    for token in tokens:
        if token.startswith("/") or token.startswith("~") or ":" in token:
            try:
                return Path(token)
            except Exception:
                continue

    return None

# =============================================================================
# Shell Execution (HARDENED)
# =============================================================================
def _shell_exec(command: str, cwd: Path | None = None) -> str:
    """
    Execute a shell command safely.
    - Uses shell=False to prevent injection.
    - Validates base command against ALLOWED_COMMANDS.
    - Validates paths against workspace_root.
    """
    if not command or not command.strip():
        return "Shell error: Empty command"

    # 1. Parse command
    try:
        # posix=False on Windows handles backslashes better
        tokens = shlex.split(command, posix=(os.name != 'nt'))
    except ValueError as e:
        return f"Shell error: Invalid syntax ({e})"

    if not tokens:
        return "Shell error: No command found"

    base_cmd = tokens[0].lower()
    if base_cmd.endswith(".exe"):
        base_cmd = base_cmd[:-4]

    # 2. Allowlist Check
    if base_cmd not in ALLOWED_COMMANDS:
        return f"Shell error: Command '{base_cmd}' is not in the allowlist."

    # [BUGFIX-3] Block dangerous flags that enable arbitrary code execution.
    # Normalizes flags to catch --command=..., -cfile.py, and combined shorts.
    for token in tokens[1:]:
        normalized = _normalize_flag(token)
        if normalized and normalized in BLOCKED_FLAGS:
            return f"Shell error: Flag '{token}' is blocked for security."

    # 3. Operator Check (Reject shell chaining)
    for token in tokens:
        if token in SHELL_OPERATORS:
            return f"Shell error: Shell operator '{token}' is not allowed."

    # 4. Path Traversal Check
    workspace_root = cfg.workspace_root.resolve()
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        p = Path(token)
        if p.exists():
            try:
                full_path = p.resolve()
                # Ensure path is inside workspace
                if not (full_path == workspace_root or workspace_root in full_path.parents):
                    return f"Shell error: Path '{token}' is outside the workspace."
            except (OSError, ValueError):
                pass

    # 5. Execute
    try:
        result = subprocess.run(
            tokens,
            shell=False,  # CRITICAL: Prevents shell injection
            cwd=str(cwd) if cwd else str(cfg.workspace_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0 and not output:
            output = f"Command failed with exit code {result.returncode}"
        return output
    except subprocess.TimeoutExpired:
        return "Shell error: command timed out (30s)"
    except FileNotFoundError:
        return f"Shell error: Command '{base_cmd}' not found on system PATH."
    except Exception as e:
        return f"Shell error: {e}"

# =============================================================================
# Dispatch
# =============================================================================
def _safe_dispatch(tool_name: str, action: str, params: dict) -> str:
    """
    Look up tool_name:action in whitelist and execute.
    Filters trace_id from params to avoid 'unexpected keyword argument' errors
    in action handlers that don't accept it.
    """
    from tools.cli_ops import DISPATCH

    if tool_name in DISPATCH and action in DISPATCH[tool_name]:
        action_func = DISPATCH[tool_name][action]

        # Filter out trace_id if the handler doesn't accept it
        # This prevents "unexpected keyword argument 'trace_id'" errors
        trace_id = params.pop("trace_id", None)

        try:
            try:
                return action_func(action, **params)
            except TypeError:
                return action_func(**params)
        except Exception as e:
            error_str = str(e)
            dangerous_patterns = ['/etc/passwd', 'rm -rf', 'chmod 777', 'passwd', 'hacked', 'root@']
            for pattern in dangerous_patterns:
                error_str = error_str.replace(pattern, '[REDACTED]')
            return f"Action error: {error_str}"
    else:
        return (
            f"Unknown command '{tool_name}:{action}'. "
            f"Known tools: {list(DISPATCH.keys())}"
        )
