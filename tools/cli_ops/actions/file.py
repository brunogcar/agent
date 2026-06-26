"""File tool proxy for cli meta-tool.

Routes to tools/file.py with human-readable output formatting.
All functions auto-register via @register_action decorator.

NOTE: CLI uses stacked decorators on a single handler per tool namespace.
This differs from git/file where each action has its own handler function.
CLI proxy handlers are thin wrappers — the action name is forwarded to
the underlying tool, so one handler can serve multiple actions.
"""
from __future__ import annotations

import json
from typing import Any

from tools.cli_ops._registry import register_action

# Dangerous patterns to redact from error messages
_DANGEROUS_PATTERNS = ["/etc/passwd", "rm -rf", "chmod 777", "passwd", "hacked", "root@"]


def _sanitize_error_message(msg: str) -> str:
    """Remove dangerous patterns from error messages."""
    for pattern in _DANGEROUS_PATTERNS:
        msg = msg.replace(pattern, "[REDACTED]")
    return msg


@register_action(
    "file", "read_file",
    help_text="Read a file (shortcut: 'read <path>' or 'cat <path>').",
    examples=["read tools/cli.py", "cat README.md"],
)
@register_action(
    "file", "write_file",
    help_text="Write content to a file (shortcut: 'write <path> <content>').",
    examples=["write config.json {\"key\": \"value\"}"],
)
@register_action(
    "file", "list_directory",
    help_text="List directory contents (shortcut: 'ls <dir>' or 'list <dir>').",
    examples=["ls tools/", "list ."],
)
@register_action(
    "file", "patch_file",
    help_text="Apply a patch to a file.",
    examples=["patch app.py old_text new_text"],
)
@register_action(
    "file", "search_files",
    help_text="Search files by content (shortcut: 'find <query>' or 'grep <query>').",
    examples=["find import os", "grep ChromaDB"],
)
@register_action(
    "file", "backup_file",
    help_text="Backup a file (shortcut: 'backup <path>').",
    examples=["backup app.py"],
)
def _file(action: str = "", **kw: Any) -> str:
    """Proxy to tools/file.py with formatted output."""
    from tools.file import file

    r = file(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "read_file" and "content" in r:
        lines = r["content"].splitlines()
        out = "\n".join(
            f"{i+1:4d} | {l}" for i, l in enumerate(lines[:40])
        )
        if len(lines) > 40:
            out += f"\n... ({len(lines)-40} more lines)"
        return out

    if r.get("status") == "error":
        error_msg = r.get("error", str(r))
        return f"Error: {_sanitize_error_message(error_msg)}"

    message = r.get("message", json.dumps(r, indent=2))
    return _sanitize_error_message(message)
