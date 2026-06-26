"""Git tool proxy for cli meta-tool.

Routes to tools/git.py with human-readable output formatting.
All functions auto-register via @register_action decorator.

NOTE: CLI uses stacked decorators on a single handler per tool namespace.
See actions/file.py for explanation.
"""
from __future__ import annotations

import json
from typing import Any

from tools.cli_ops._registry import register_action


@register_action(
    "git", "status",
    help_text="Show working tree status (shortcut: 'git status').",
    examples=["git status"],
)
@register_action(
    "git", "log",
    help_text="Show commit history (shortcut: 'git log [N]').",
    examples=["git log", "git log 10"],
)
@register_action(
    "git", "diff",
    help_text="Show unstaged changes (shortcut: 'git diff').",
    examples=["git diff"],
)
@register_action(
    "git", "snapshot",
    help_text="Create a safe checkpoint commit (shortcut: 'git snapshot [msg]').",
    examples=["git snapshot", "git snapshot before refactor"],
)
@register_action(
    "git", "commit",
    help_text="Stage all and commit (shortcut: 'git commit <msg>').",
    examples=["git commit fix bug in cli"],
)
@register_action(
    "git", "rollback",
    help_text="Reset to HEAD (shortcut: 'git rollback [--force]').",
    examples=["git rollback", "git rollback --force"],
)
def _git(action: str = "", **kw: Any) -> str:
    """Proxy to tools/git.py with formatted output."""
    from tools.git import git

    r = git(action=action, **kw)
    if not isinstance(r, dict):
        return str(r)

    if action == "log":
        cs = r.get("commits", [])
        lines = []
        for c in cs[:10]:
            h = c.get("hash", "")[:7]
            m = c.get("message", "").splitlines()[0][:70]
            lines.append(f"{h} {m}")
        return "\n".join(lines) or "No commits."

    if action == "diff":
        return r.get("diff", str(r))

    if r.get("status") == "error":
        err = r.get("error", r)
        return f"Error: {err}"

    return r.get("message", json.dumps(r))
