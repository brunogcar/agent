"""
helpers.py — Shared helper functions for cli meta-tool.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.config import cfg

# ── Input Sanitization ───────────────────────────────────────────────────────
_MAX_COMMAND_LENGTH = 2048
_MAX_ARGUMENTS = 20
_CONTROL_CHAR_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f]')

def _sanitize_command(command: str) -> str:
    """
    Sanitize command input before processing.

    Rejects:
    - Commands exceeding max length
    - Commands containing null bytes
    - Commands with control characters
    - Commands with too many arguments
    """
    if not isinstance(command, str):
        raise ValueError("Command must be a string")

    # Check length
    if len(command) > _MAX_COMMAND_LENGTH:
        raise ValueError(f"Command too long (max {_MAX_COMMAND_LENGTH} chars)")

    # Check for null bytes
    if '\x00' in command:
        raise ValueError("Command contains null bytes")

    # Check for control characters
    if _CONTROL_CHAR_PATTERN.search(command):
        raise ValueError("Command contains control characters")

    # Normalize whitespace (multiple spaces -> single)
    command = ' '.join(command.split())

    # Check argument count
    args = command.split()
    if len(args) > _MAX_ARGUMENTS:
        raise ValueError(f"Too many arguments (max {_MAX_ARGUMENTS})")

    return command

# ── Lazy memory accessor ─────────────────────────────────────────────────────
def _mem():
    """Lazy import of ChromaDB store — avoids slow startup."""
    from core.memory import memory as _store
    return _store

# ── Shell whitelist constants ────────────────────────────────────────────────
_SHELL_ALLOW: dict[str, list[str]] = {
    # Read-only info commands
    "python":      None,
    "pip":         ["pip", "--version"],
    "whoami":      ["whoami"],
    "hostname":    ["hostname"],
    "ver":         ["cmd", "/c", "ver"],
    "systeminfo":  ["systeminfo"],
    "ipconfig":    ["ipconfig"],
    "tasklist":    ["tasklist"],
    "where":       ["where"],
    "which":       ["which"],
    "dir":         ["cmd", "/c", "dir"],
    "ls":          ["cmd", "/c", "dir"] if sys.platform == "win32" else ["ls", "-la"],
    "type":        ["cmd", "/c", "type"],
    "cat":         ["cat"],
    "env":         ["cmd", "/c", "set"] if sys.platform == "win32" else ["env"],
    "set":         ["cmd", "/c", "set"],
    "echo":        None,
    # File operation commands
    "copy":        ["cmd", "/c", "copy"],
    "xcopy":       ["cmd", "/c", "xcopy"],
    "move":        ["cmd", "/c", "move"],
    "mkdir":       ["cmd", "/c", "mkdir"] if sys.platform == "win32" else ["mkdir", "-p"],
    "md":          ["cmd", "/c", "mkdir"],
    "rmdir":       ["cmd", "/c", "rmdir"],
    "rd":          ["cmd", "/c", "rmdir"],
    "del":         ["cmd", "/c", "del"],
    "rm":          ["rm"],
    "cp":          ["cp"],
    "mv":          ["mv"],
}

_SHELL_PASSTHROUGH = {
    "python", "pip", "where", "which", "dir", "ls", "type", "cat",
    "copy", "xcopy", "move", "mkdir", "md", "rmdir", "rd", "del",
    "rm", "cp", "mv",
}

_SHELL_MAX_OUTPUT = 4096
_SHELL_TIMEOUT = 15

_SHELL_AGENT_FALLBACK: dict[str, tuple[str, str, Any]] = {
    "dir":   ("file", "list",   lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else "."}),
    "ls":    ("file", "list",   lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else "."}),
    "type":  ("file", "read",   lambda cmd: {"path": " ".join(cmd.split()[1:])}),
    "cat":   ("file", "read",   lambda cmd: {"path": " ".join(cmd.split()[1:])}),
    "copy":  ("file", "backup", lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else ""}),
    "cp":    ("file", "backup", lambda cmd: {"path": cmd.split()[1] if len(cmd.split()) > 1 else ""}),
}

# ── Enhanced Working Directory Detection ──────────────────────────────────────
def _detect_cwd(command: str) -> Path:
    """
    Auto-detect working directory from command context.

    The agent operates in two root contexts:
      - agent root    (D:/mcp/agent)      -- agent code, tools, skills
      - workspace root (D:/mcp/workspace) -- project work, output files

    Heuristic (first match wins):
      1. Command contains an absolute path -> use its parent dir
      2. Command contains "workspace/" or "workspace\" -> workspace root
      3. Command contains "agent/" or "agent\" -> agent root
      4. Command starts with "cd workspace" -> workspace root
      5. Command starts with "cd agent" -> agent root
      6. Default -> agent root
    """
    # Check for absolute path tokens in the command
    for token in command.split():
        p = Path(token.strip('"').strip("'"))
        if p.is_absolute():
            if p.is_dir():
                return p
            if p.parent.is_dir():
                return p.parent

    cmd_lower = command.lower()

    # Check for explicit cd commands
    if cmd_lower.startswith("cd workspace"):
        return cfg.workspace_root
    if cmd_lower.startswith("cd agent"):
        return cfg.agent_root

    # Check for path prefixes
    if "workspace/" in cmd_lower or "workspace\\" in cmd_lower:
        return cfg.workspace_root
    if "agent/" in cmd_lower or "agent\\" in cmd_lower:
        return cfg.agent_root

    # Default to agent root
    return cfg.agent_root

# ── Shell executor ───────────────────────────────────────────────────────────
def _shell_exec(command: str) -> str | None:
    """
    Try to execute `command` as a whitelisted shell command.

    Returns:
      str  -- command output (or error message) if command is whitelisted.
      None -- command not whitelisted; caller should fall through to next layer.
    """
    parts = command.strip().split()
    if not parts:
        return None

    cmd_name = parts[0].lower()
    if cmd_name.endswith(".exe"):
        cmd_name = cmd_name[:-4]

    if cmd_name not in _SHELL_ALLOW or _SHELL_ALLOW[cmd_name] is None:
        if cmd_name == "python":
            import shutil as _shutil
            py_exe = _shutil.which("python") or "python"
            if len(parts) == 1:
                argv = [py_exe, "--version"]
            elif parts[1].endswith(".py") or parts[1].startswith("-"):
                argv = [py_exe] + parts[1:]
            else:
                argv = [py_exe, "--version"]
            cwd = _detect_cwd(command)
            try:
                result = subprocess.run(
                    argv, capture_output=True, text=True,
                    cwd=str(cwd), timeout=60,
                )
                out = (result.stdout + result.stderr).strip()
                if len(out) > _SHELL_MAX_OUTPUT:
                    out = out[:_SHELL_MAX_OUTPUT] + f"\n... (truncated)"
                return out if out else "(python completed, no output)"
            except subprocess.TimeoutExpired:
                return f"python script timed out after 60s"
            except Exception as e:
                return f"python error: {e}"
        return None

    base = _SHELL_ALLOW[cmd_name]
    if cmd_name in _SHELL_PASSTHROUGH:
        argv = base + parts[1:] if base else parts
    else:
        argv = list(base)

    cwd = _detect_cwd(command)

    shell_error = ""
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=_SHELL_TIMEOUT,
        )
        out = (result.stdout + result.stderr).strip()
        if len(out) > _SHELL_MAX_OUTPUT:
            out = out[:_SHELL_MAX_OUTPUT] + f"\n... (truncated at {_SHELL_MAX_OUTPUT} chars)"

        if result.returncode == 0:
            return out if out else "(command completed, no output)"

        shell_error = out or f"(exit code {result.returncode})"

    except FileNotFoundError:
        shell_error = f"Command not found: {parts[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {_SHELL_TIMEOUT}s: {command}"
    except Exception as e:
        shell_error = f"Shell error: {e}"

    if cmd_name in _SHELL_AGENT_FALLBACK:
        tool_name, action, param_fn = _SHELL_AGENT_FALLBACK[cmd_name]
        try:
            from tools.cli_ops.actions import DISPATCH
            params = param_fn(command)
            fallback_result = _safe_dispatch(tool_name, action, params)
            if fallback_result and not fallback_result.startswith("Unknown command"):
                return f"[shell failed, agent fallback]\n{fallback_result}"
        except Exception:
            pass

    return shell_error

# ── Safe dispatch ─────────────────────────────────────────────────────────────
def _safe_dispatch(tool_name: str, action: str, params: dict) -> str:
    """Look up tool_name:action in whitelist and execute. Never raises."""
    from tools.cli_ops.actions import DISPATCH

    key = f"{tool_name.lower()}:{action.lower()}"
    fn = DISPATCH.get(key)
    if fn is None:
        available = [k for k in DISPATCH if k.startswith(tool_name.lower() + ":")]
        hint = f" Available for '{tool_name}': {available}" if available else \
               f" Known tools: {sorted({k.split(':')[0] for k in DISPATCH})}"
        return f"Unknown command '{key}'.{hint}"
    try:
        return fn(**params)
    except Exception as e:
        return f"Error in {key}: {e}"