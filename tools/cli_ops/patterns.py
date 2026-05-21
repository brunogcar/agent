"""
patterns.py — Pattern matching logic for cli meta-tool.

Contains regex patterns for Layer 1 (zero LLM token) command dispatch.
Order matters: more specific patterns before broad ones.
"""

from __future__ import annotations

import re
from typing import Any

_PATTERNS = [
    # System
    (r"^health$",                        "system",  "health",   lambda m: {}),
    (r"^help$",                          "system",  "help",     lambda m: {}),

    # Git operations
    (r"^git\s+status$",                  "git",     "status",   lambda m: {}),
    (r"^git\s+log\s+(\d+)",              "git",     "log",      lambda m: {"n": int(m.group(1))}),
    (r"^git\s+log$",                     "git",     "log",      lambda m: {}),
    (r"^git\s+diff$",                    "git",     "diff",     lambda m: {}),
    (r"^git\s+snapshot\s*(.*)",          "git",     "snapshot", lambda m: {"message": m.group(1).strip() or ""}),
    (r"^git\s+commit\s+(.+)",            "git",     "commit",   lambda m: {"message": m.group(1).strip()}),
    (r"^git\s+rollback\s+--?force$",     "git",     "rollback", lambda m: {"force": True}),
    (r"^git\s+rollback$",                "git",     "rollback", lambda m: {}),

    # Web operations - MOVED BEFORE FILE
    (r"^search\s+(.+)",                  "web",     "search",   lambda m: {"query": m.group(1).strip()}),
    (r"^scrape\s+(https?://\S+)",        "web",     "scrape",   lambda m: {"url": m.group(1).strip()}),
    (r"^read\s+(https?://\S+)",          "web",     "read",     lambda m: {"url": m.group(1).strip()}),

    # File operations
    (r"^(?:read|cat|show)\s+(.+)",       "file",    "read",     lambda m: {"path": m.group(1).strip()}),
    (r"^(?:ls|list)\s*(.*)",             "file",    "list",     lambda m: {"path": m.group(1).strip() or "."}),
    (r"^write\s+(\S+)\s+(.+)",           "file",    "write",    lambda m: {"path": m.group(1), "content": m.group(2)}),
    (r"^(?:find|grep)\s+(.+)",           "file",    "search",   lambda m: {"query": m.group(1).strip()}),
    (r"^backup\s+(\S+)",                "file",    "backup",   lambda m: {"path": m.group(1).strip()}),

    # Memory operations
    (r"^recall\s+(.+)",                  "memory",  "recall",   lambda m: {"query": m.group(1).strip()}),
    (r"^store\s+(.+)",                   "memory",  "store",    lambda m: {"text": m.group(1).strip()}),
    (r"^memory\s+stats$",                "memory",  "stats",    lambda m: {}),
    (r"^memory\s+prune$",                "memory",  "prune",    lambda m: {}),

    # Python operations
    (r"^calc\s+(.+)",                    "python",  "calc",     lambda m: {"code": m.group(1).strip()}),
    (r"^(?:run|exec)\s+(.+)",            "python",  "run",      lambda m: {"code": m.group(1).strip()}),
    # FIXED: Use double quotes in output for double-quoted input
    (r'echo\s+"([^"]+)"',                "python",  "run",      lambda m: {"code": f'print("{m.group(1)}")'}),
    (r"echo\s+'([^']+)'",               "python",  "run",      lambda m: {"code": f"print('{m.group(1)}')"}),  # FIXED: use single quotes
    (r"^echo\s+(.*)",                   "python",  "run",      lambda m: {"code": f'print({m.group(1).strip()!r})'}),

    # Notify
    (r"^(?:notify|alert|ping)\s+(.+)",  "notify",  "send",     lambda m: {"message": m.group(1).strip()}),

    # Skill calls
    (r"^skill\s+(\w+)\s+(\w+)\s+(\S+)$", "skill", "call",
        lambda m: {"domain": m.group(1), "mode": m.group(2), "arg": m.group(3)}),
    (r"^skill\s+(\w+)\s+(\w+)$",          "skill", "call",
        lambda m: {"domain": m.group(1), "mode": m.group(2), "arg": ""}),

    # LMS operations
    (r"^lms\s+ls$",                      "lms",     "ls",       lambda m: {}),
    (r"^lms\s+ps$",                      "lms",     "ps",       lambda m: {}),
    (r"^lms\s+load\s+(.+)",              "lms",     "load",     lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload\s+(.+)",            "lms",     "unload",   lambda m: {"model": m.group(1).strip()}),
    (r"^lms\s+unload$",                  "lms",     "unload",   lambda m: {}),
    (r"^lms\s+log$",                     "lms",     "log",      lambda m: {}),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), tn, a, fn)
             for p, tn, a, fn in _PATTERNS]

def _match_pattern(command: str):
    """Returns (tool_name, action, params) or None."""
    for rx, tool_name, action, param_fn in _COMPILED:
        m = rx.match(command.strip())
        if m:
            return tool_name, action, param_fn(m)
    return None