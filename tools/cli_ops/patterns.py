"""Pattern matching logic for cli meta-tool (Layer 1).

Contains regex patterns for zero-LLM-token command dispatch.
Order matters: more specific patterns before broad ones.

All action names must match the current DISPATCH keys in the refactored
tools (e.g., "read_file" not "read"). Stale names will cause dispatch
failures.
"""
from __future__ import annotations

import re
from typing import Any

_PATTERNS = [
    # System
    (r"^health$", "system", "health", lambda m: {}),
    (r"^help$", "system", "help", lambda m: {}),

    # Cleanup operations
    (r"^cleanup\s+autocode\s+(\d+)\s+days$", "cleanup", "autocode",
     lambda m: {"days": int(m.group(1))}),
    (r"^cleanup\s+autocode\s+(\d+)$", "cleanup", "autocode",
     lambda m: {"days": int(m.group(1))}),
    (r"^cleanup\s+autocode$", "cleanup", "autocode", lambda m: {}),
    (r"^clean\s+autocode\s+(\d+)\s+days$", "cleanup", "autocode",
     lambda m: {"days": int(m.group(1))}),
    (r"^clean\s+autocode$", "cleanup", "autocode", lambda m: {}),
    (r"^dry\s+run\s+cleanup\s+autocode$", "cleanup", "dry_run", lambda m: {}),
    (r"^dry\s+run\s+cleanup$", "cleanup", "dry_run", lambda m: {}),

    # Git operations — action names match refactored git tool DISPATCH
    (r"^git\s+status$", "git", "status", lambda m: {}),
    (r"^git\s+log\s+(\d+)", "git", "log", lambda m: {"n": int(m.group(1))}),
    (r"^git\s+log$", "git", "log", lambda m: {}),
    (r"^git\s+diff$", "git", "diff", lambda m: {}),
    (r"^git\s+snapshot\s*(.*)", "git", "snapshot",
     lambda m: {"message": m.group(1).strip() or ""}),
    (r"^git\s+commit\s+(.+)", "git", "commit",
     lambda m: {"message": m.group(1).strip()}),
    (r"^git\s+rollback\s+--?force$", "git", "rollback",
     lambda m: {"force": True}),
    (r"^git\s+rollback$", "git", "rollback", lambda m: {}),

    # Web operations — MOVED BEFORE FILE to avoid "read" collision
    (r"^search\s+(.+)", "web", "search", lambda m: {"query": m.group(1).strip()}),
    (r"^scrape\s+(https?://\S+)", "web", "scrape",
     lambda m: {"url": m.group(1).strip()}),
    (r"^read\s+(https?://\S+)", "web", "read",
     lambda m: {"url": m.group(1).strip()}),

    # File operations — action names match refactored file tool DISPATCH
    (r"^(?:read|cat|show)\s+(.+)", "file", "read_file",
     lambda m: {"path": m.group(1).strip()}),
    (r"^(?:ls|list)\s*(.*)", "file", "list_directory",
     lambda m: {"path": m.group(1).strip() or "."}),
    (r"^write\s+(\S+)\s+(.+)", "file", "write_file",
     lambda m: {"path": m.group(1), "content": m.group(2)}),
    (r"^(?:find|grep)\s+(.+)", "file", "search_files",
     lambda m: {"query": m.group(1).strip()}),
    (r"^backup\s+(\S+)", "file", "backup_file",
     lambda m: {"path": m.group(1).strip()}),

    # Memory operations
    (r"^recall\s+(.+)", "memory", "recall", lambda m: {"query": m.group(1).strip()}),
    (r"^store\s+(.+)", "memory", "store", lambda m: {"text": m.group(1).strip()}),
    (r"^memory\s+stats$", "memory", "stats", lambda m: {}),
    (r"^memory\s+prune$", "memory", "prune", lambda m: {}),

    # Python operations
    (r"^calc\s+(.+)", "python", "calc", lambda m: {"code": m.group(1).strip()}),
    (r"^(?:run|exec)\s+(.+)", "python", "run", lambda m: {"code": m.group(1).strip()}),
    (r'echo\s+"([^"]+)"', "python", "run",
     lambda m: {"code": f'print("{m.group(1)}")'}),
    (r"echo\s+'([^']+)'", "python", "run",
     lambda m: {"code": f"print('{m.group(1)}')"}),
    (r"^echo\s+(.*)", "python", "run",
     lambda m: {"code": f"print({m.group(1).strip()!r})"}),

    # Notify
    (r"^(?:notify|alert|ping)\s+(.+)", "notify", "send",
     lambda m: {"message": m.group(1).strip()}),

    # Skill calls
    (r"^skill\s+(\w+)\s+(\w+)\s+(\S+)$", "skill", "call",
     lambda m: {"domain": m.group(1), "mode": m.group(2), "arg": m.group(3)}),
    (r"^skill\s+(\w+)\s+(\w+)$", "skill", "call",
     lambda m: {"domain": m.group(1), "mode": m.group(2), "arg": ""}),

    # LMS operations
    (r"^lms\s+ls$", "lms", "ls", lambda m: {}),
    (r"^lms\s+ps$", "lms", "ps", lambda m: {}),
    (r"^lms\s+load\s+(.+)", "lms", "load",
     lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload\s+(.+)", "lms", "unload",
     lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload$", "lms", "unload", lambda m: {}),
    (r"^lms\s+log$", "lms", "log", lambda m: {}),
]

_COMPILED = [
    (re.compile(p, re.IGNORECASE), tn, a, fn)
    for p, tn, a, fn in _PATTERNS
]


def _match_pattern(command: str):
    """Match a natural-language command against known patterns.

    Returns:
        (tool_name, action, params) tuple if matched, or None.
    """
    for rx, tool_name, action, param_fn in _COMPILED:
        m = rx.match(command.strip())
        if m:
            return tool_name, action, param_fn(m)
    return None
