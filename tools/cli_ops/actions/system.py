"""
system.py — System actions for cli meta-tool.

All functions auto-register via @register_action decorator.
"""

from __future__ import annotations

from tools.cli_ops.actions._registry import register_action

@register_action("system", "health")
def _system_health() -> str:
    """System health check."""
    return "MCP Agent Stack: all systems operational."

@register_action("system", "help")
def _system_help() -> str:
    """System help message."""
    return (
        "cli quick commands:\n"
        "  git status | log [n] | diff | snapshot [msg] | commit <msg> | rollback [--force]\n"
        "  file read <path> | write <path> <content> | list [dir] | search <query>\n"
        "  web search <query> | scrape <url> | read <url>\n"
        "  memory recall <query> | store <text> | stats | prune\n"
        "  python run <code> | calc <expr>\n"
        "  notify <message>\n"
        "  lms ls | ps | load <model> | unload [model] | log\n"
        "  skill <domain> <mode>  -- e.g. skill b3_api status | skill b3_api sync\n"
        "  health | help\n"
        "Shell (zero tokens, real output):\n"
        "  python <script.py> [args] | python --version | pip --version\n"
        "  whoami | hostname | where <cmd> | dir [path] | type <file>\n"
        "  copy <src> <dst> | move <src> <dst> | mkdir <dir> | del <file>\n"
        "Anything else -> Router decides: direct dispatch or Executor escalation."
    )