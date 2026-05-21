"""Proxy to tools/file.py with formatted output and sanitized errors."""

from __future__ import annotations

import json
from typing import Any

from tools.cli_ops._registry import register_action

# Dangerous patterns to redact from error messages
_DANGEROUS_PATTERNS = ['/etc/passwd', 'rm -rf', 'chmod 777', 'passwd', 'hacked', 'root@']

def _sanitize_error_message(msg: str) -> str:
    """Remove dangerous patterns from error messages."""
    for pattern in _DANGEROUS_PATTERNS:
        msg = msg.replace(pattern, '[REDACTED]')
    return msg

@register_action("file", "read")
@register_action("file", "write")
@register_action("file", "list")
@register_action("file", "patch")
@register_action("file", "search")
@register_action("file", "backup")
def _file(action: str, **kw: Any) -> str:
    """Proxy to tools/file.py with formatted output."""
    from tools.file import file

    r = file(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "read" and "content" in r:
        lines = r["content"].splitlines()
        out = "\n".join(f"{i+1:4d} | {l}" for i, l in enumerate(lines[:40]))
        if len(lines) > 40:
            out += f"\n... ({len(lines)-40} more lines)"
        return out

    if r.get("status") == "error":
        # Sanitize error message before returning
        error_msg = r.get('error', str(r))
        return f"Error: {_sanitize_error_message(error_msg)}"

    # Sanitize message output as well
    message = r.get("message", json.dumps(r, indent=2))
    return _sanitize_error_message(message)