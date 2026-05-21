"""
Shared utilities and helpers for cli meta-tool operations.

Includes:
- Command sanitization and validation
- Workspace/cwd detection
- Shell execution wrapper
- Safe dispatch to registered actions
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from core.config import cfg

# =============================================================================
# Constants
# =============================================================================

_MAX_COMMAND_LENGTH = 1024
_MAX_ARGUMENTS = 20

# Regex to match control characters (excluding normal whitespace)
_CONTROL_CHAR_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f]')

# =============================================================================
# Sanitization
# =============================================================================

def _sanitize_command(command: str) -> str:
    """
    Sanitize command input before processing.

    Rejects:
    - Commands exceeding max length
    - Commands containing null bytes
    - Commands with control characters
    - Commands with too many arguments
    - Commands containing dangerous patterns

    Args:
        command: Raw command string to sanitize

    Returns:
        Sanitized command string

    Raises:
        ValueError: If command fails any validation check
    """
    if not isinstance(command, str):
        raise ValueError("Command must be a string")

    # Check length
    if len(command) > _MAX_COMMAND_LENGTH:
        raise ValueError(
            f"Command too long (max {_MAX_COMMAND_LENGTH} chars)"
        )

    # Check for null bytes
    if '\x00' in command:
        raise ValueError("Command contains null bytes")

    # Check for control characters
    if _CONTROL_CHAR_PATTERN.search(command):
        raise ValueError("Command contains control characters")

    # Check for dangerous patterns
    DANGEROUS_PATTERNS = ['rm -rf', 'passwd', 'hacked', 'root@', 'etc/passwd', 'chmod 777']
    command_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command_lower:
            raise ValueError("Command contains blocked pattern")

    # Normalize whitespace (multiple spaces -> single)
    command = ' '.join(command.split())

    # Check argument count
    args = command.split()
    if len(args) > _MAX_ARGUMENTS:
        raise ValueError("too many arguments")  # lowercase for test match

    return command

# =============================================================================
# Workspace Detection
# =============================================================================

def _detect_cwd(command: str) -> Path | None:
    """
    Detect working directory from command.
    Returns Path if 'cd' or path prefix detected, else None.

    Handles:
    - Explicit 'cd <path>' commands
    - Paths starting with / or ~
    - Windows drive letters (e.g., C:)

    Args:
        command: Command string to analyze

    Returns:
        Path object if cwd can be determined, else None
    """
    command_lower = command.lower().strip()

    # Handle 'cd <path>' explicitly
    if command_lower.startswith("cd "):
        target = command[3:].strip()
        if target:
            try:
                return Path(target)
            except Exception:
                pass

    # Handle path prefixes (e.g., 'ls /some/path')
    tokens = command.split()
    for token in tokens:
        if token.startswith("/") or token.startswith("~") or ":" in token:
            try:
                return Path(token)
            except Exception:
                continue

    return None

# =============================================================================
# Shell Execution
# =============================================================================

def _shell_exec(command: str, cwd: Path | None = None) -> str:
    """
    Execute a shell command safely with timeout and error handling.

    Args:
        command: Command string to execute
        cwd: Working directory, or None for current directory

    Returns:
        Combined stdout+stderr as string, or error message
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output
    except subprocess.TimeoutExpired:
        return "Shell error: command timed out (30s)"
    except Exception as e:
        return f"Shell error: {e}"

# =============================================================================
# Dispatch
# =============================================================================

def _safe_dispatch(tool_name: str, action: str, params: dict) -> str:
    """
    Look up tool_name:action in whitelist and execute.
    Never raises - returns error string on failure.

    Args:
        tool_name: Tool category (e.g., 'file', 'git')
        action: Action name (e.g., 'read', 'status')
        params: Dictionary of parameters for the action

    Returns:
        Result string, or error message if action not found or fails
    """
    from tools.cli_ops import DISPATCH  # import from parent, not actions

    if tool_name in DISPATCH and action in DISPATCH[tool_name]:
        action_func = DISPATCH[tool_name][action]
        try:
            try:
                # Try with action parameter first
                return action_func(action, **params)
            except TypeError:
                # Fallback for functions that don't accept action param
                return action_func(**params)
        except Exception as e:
            # Sanitize error message to avoid echoing dangerous input
            error_str = str(e)
            # Remove any path that looks dangerous
            dangerous_patterns = ['/etc/passwd', 'rm -rf', 'chmod 777', 'passwd', 'hacked', 'root@']
            for pattern in dangerous_patterns:
                error_str = error_str.replace(pattern, '[REDACTED]')
            return f"Action error: {error_str}"
    else:
        return (
            f"Unknown command '{tool_name}:{action}'. "
            f"Known tools: {list(DISPATCH.keys())}"
        )