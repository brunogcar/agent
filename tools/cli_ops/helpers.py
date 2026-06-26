"""Shared utilities and helpers for cli meta-tool operations.

Includes:
  - Command sanitization and validation
  - Secure shell execution wrapper (shell=False + allowlist)
  - Safe dispatch to registered proxy actions
  - Path guard integration via core.path_guard

Security model:
  - shell=False prevents shell injection (no chaining via ; | &&)
  - ALLOWED_COMMANDS whitelist controls which binaries run
  - BLOCKED_FLAGS blacklist prevents arbitrary code execution (python -c, etc.)
  - core.path_guard.resolve_path validates all filesystem paths before execution

Design note: DANGEROUS_PATTERNS uses substring matching, which may block
safe-looking strings (e.g., 'echo "don\'t rm -rf /"'). This is an
acceptable false-positive tradeoff — better to block a safe command than
allow a dangerous one. Future AIs: do not "fix" this by making it
regex-based or more permissive without security review.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from core.config import cfg
from core.path_guard import resolve_path, _is_within

# =============================================================================
# Constants
# =============================================================================

_CONTROL_CHAR_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f]')

# Base commands allowed for execution. shell=False prevents chaining.
# SECURITY: This is an allowlist, not a blocklist. Any command not listed
# here is rejected before execution.
#
# NOTE on 'python'/'python3': These are allowed but BLOCKED_FLAGS prevents
# -c, -m, --command, --module flags. An attacker can still run
# 'python malicious_script.py' if the script is inside AGENT_ROOT.
# This is an accepted risk — path guard limits it to AGENT_ROOT, and
# the agent already has full filesystem access within that boundary.
# Future AIs: do NOT remove python from the allowlist without providing
# an alternative for running scripts.
ALLOWED_COMMANDS = frozenset({
    # File/Dir ops
    "ls", "dir", "cat", "type", "head", "tail", "grep", "findstr",
    "wc", "cp", "copy", "mv", "move", "mkdir", "rmdir",
    "touch", "stat", "du", "df", "pwd", "cd",
    # Git & Dev
    "git", "gh", "python", "python3", "pip", "pytest",
    # Text/System
    "uname", "whoami", "date", "echo", "which", "where",
    "systeminfo", "ipconfig", "hostname", "tasklist", "ver",
    "diff", "md5sum", "sha256sum",
})

# Shell operators that are dangerous or useless with shell=False
SHELL_OPERATORS = {"|", "||", "&&", ";", ">", ">>", "<", "&", "`", "$("}

# Dangerous flags that enable arbitrary code execution even when
# the base command is allowlisted (e.g., "python -c 'import os; os.system(...)'").
# These flags are checked after normalization (handles --command=..., -cfile.py, etc.)
#
# NOTE: -m blocks 'python -m pytest', but 'pytest' is standalone in
# ALLOWED_COMMANDS. This is intentional defense-in-depth — if someone
# accidentally allows 'python -m' in the future, the flag block still
# catches it. Future AIs: do NOT remove -m from BLOCKED_FLAGS.
BLOCKED_FLAGS = frozenset({"-c", "-m", "--command", "--module", "-e", "--eval"})

# Dangerous command patterns to block at sanitization time.
# SECURITY: This is a substring blocklist. It may produce false positives
# (e.g., 'echo "don\'t rm -rf /"' gets blocked). This is by design.
# See module docstring for rationale.
DANGEROUS_PATTERNS = frozenset({
    "rm -rf", "passwd", "hacked", "root@", "etc/passwd", "chmod 777",
    "del /f", "format", "diskpart", "rd /s", "rmdir /s",
})

# Redaction patterns for error messages — must match DANGEROUS_PATTERNS
# exactly. Future AIs: keep these in sync with DANGEROUS_PATTERNS.
_REDACTION_PATTERNS = [
    "/etc/passwd", "rm -rf", "chmod 777", "passwd",
    "hacked", "root@",
]


def _normalize_flag(token: str) -> str | None:
    """Normalize a CLI token to its canonical flag form for blacklist checking.

    Handles:
    --flag=value → --flag
    -cfile.py → -c
    --co → --co (argparse prefix, not matched unless in BLOCKED_FLAGS)
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
    """Sanitize command input before processing.

    Raises:
        ValueError: On null bytes, control characters, blocked patterns,
        excessive length, or too many arguments.
    """
    if not isinstance(command, str):
        raise ValueError("Command must be a string")

    if len(command) > cfg.cli_max_command_chars:
        raise ValueError(
            f"Command too long (max {cfg.cli_max_command_chars} chars)"
        )

    if "\x00" in command:
        raise ValueError("Command contains null bytes")

    if _CONTROL_CHAR_PATTERN.search(command):
        raise ValueError("Command contains control characters")

    command_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command_lower:
            raise ValueError(f"Command contains blocked pattern: {pattern}")

    command = " ".join(command.split())

    args = command.split()
    if len(args) > cfg.cli_max_arguments:
        raise ValueError("too many arguments")

    return command


# =============================================================================
# Shell Execution (HARDENED)
# =============================================================================

def _shell_exec(command: str, cwd: Path | None = None) -> str:
    """Execute a whitelisted shell command safely.

    Security layers:
    1. Parse via shlex (no shell injection)
    2. Validate base command against ALLOWED_COMMANDS
    3. Block dangerous flags (python -c, etc.)
    4. Reject shell operators (| ; && etc.)
    5. Validate all non-flag tokens via core.path_guard (default_root="agent")
    6. Execute with shell=False, capped output, 30s timeout

    Args:
        command: The shell command string to execute.
        cwd: Optional working directory. Defaults to cfg.workspace_root.

    Returns:
        Command stdout/stderr as string, or error message prefixed with "Shell error:".
    """
    if not command or not command.strip():
        return "Shell error: Empty command"

    # 1. Parse command
    try:
        tokens = shlex.split(command, posix=(os.name != "nt"))
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

    # 3. Block dangerous flags
    for token in tokens[1:]:
        normalized = _normalize_flag(token)
        if normalized and normalized in BLOCKED_FLAGS:
            return f"Shell error: Flag '{token}' is blocked for security."

    # 4. Operator Check (Reject shell chaining)
    for token in tokens:
        if token in SHELL_OPERATORS:
            return f"Shell error: Shell operator '{token}' is not allowed."

    # 5. Path Guard — validate all non-flag tokens via core.path_guard
    # SECURITY: We validate against BOTH agent_root and workspace_root.
    # The file/git tools allow operations in either root. Blocking
    # workspace_root paths here would contradict those tools.
    agent_root = cfg.agent_root.resolve()
    workspace_root = cfg.workspace_root.resolve()
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        # SECURITY: Also parse --flag=value syntax and validate the value
        # portion if it looks like a path.
        value_token = token
        if "=" in token and not token.startswith("--"):
            # Already handled by _normalize_flag above; skip for path validation
            pass
        elif "=" in token:
            # --flag=/some/path — validate the path portion
            value_token = token.split("=", 1)[1]

        try:
            resolved, err = resolve_path(value_token, default_root="agent")
        except Exception as e:
            return f"Shell error: Path validation failed for '{value_token}': {e}"
        if err:
            # Token is not a path (e.g., "--version", "hello") — harmless, skip
            continue
        if not (_is_within(resolved, agent_root) or _is_within(resolved, workspace_root)):
            return (
                f"Shell error: Path '{value_token}' resolves outside AGENT_ROOT. "
                f"Use paths relative to the project or workspace."
            )

    # 6. Execute
    try:
        result = subprocess.run(
            tokens,
            shell=False,
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
    """Look up tool_name:action in DISPATCH and execute.

    Extracts trace_id from params without mutating the caller's dict,
    then calls the handler with the remaining params.

    Args:
        tool_name: Namespace in DISPATCH (e.g., "file", "git").
        action: Action name within the namespace.
        params: Keyword arguments for the handler. May include trace_id.

    Returns:
        Handler result (str) or error message.
    """
    from tools.cli_ops._registry import DISPATCH

    if tool_name in DISPATCH and action in DISPATCH[tool_name]:
        action_func = DISPATCH[tool_name][action]["func"]

        # Extract trace_id without mutating caller's dict
        dispatch_params = dict(params)
        dispatch_params.pop("trace_id", None)

        try:
            return action_func(action=action, **dispatch_params)
        except Exception as e:
            error_str = str(e)
            # Redact dangerous patterns from error messages before returning.
            # Uses the same patterns as DANGEROUS_PATTERNS for consistency.
            for pattern in _REDACTION_PATTERNS:
                error_str = error_str.replace(pattern, "[REDACTED]")
            return f"Action error: {error_str}"
    else:
        return (
            f"Unknown command '{tool_name}:{action}'. "
            f"Known tools: {list(DISPATCH.keys())}"
        )
