"""
tools/cli.py — Fast natural-language command dispatcher, registered as an MCP tool.

WHAT THIS IS
A single MCP tool `cli(command)` that lets the agent (or you) run simple
operations instantly without burning Planner tokens on a full workflow cycle.

HOW IT WORKS — FOUR LAYERS
1. Pattern match  — regex rules cover ~90% of common commands. Zero LLM calls.
   Returns immediately. Handles: git, file, web, memory, calc,
   echo, lms, health, help.
2. Shell whitelist — read-only and file-management shell commands executed via
   subprocess with a strict allowlist. Zero LLM calls. Real output.
   Read-only: python --version, whoami, where, dir/ls, type/cat,
                systeminfo, ipconfig, hostname, tasklist, ver
   File ops:  copy, xcopy, move, mkdir, rmdir, del
3. Router route — anything that doesn't match a pattern goes to the Router
   model with a strict JSON-only prompt.
   Router returns one of two things:
   a) {tool_name, action, params} -> execute directly via whitelist
   b) {escalate: true, reason: "..."} -> hand off to Executor
4. Executor escalation — if Router decides the command is too complex for a
   direct tool call, the command is sent to the Executor model
   as a free-form task. Executor reasons and responds.

SAFETY
- Layer 1 (patterns) and layer 2 (shell whitelist) are zero-token execution.
- Layer 2 uses subprocess with a command allowlist -- no arbitrary shell injection.
  Commands are split by shlex. Output is capped at 4KB to stay within MCP limits.
- Layer 3 (Router dispatch) uses a strict tool:action whitelist.
- Layer 4 (Executor) only produces text -- it does not call tools directly.

NAMING CONVENTION
Internal dispatch uses `tool_name` (never `tool`) to avoid shadowing the
`tool` decorator from registry.
"""
from __future__ import annotations

import os
import shlex

from registry import tool
from core.config import cfg

# Import from cli_ops package
from tools.cli_ops.helpers import (
    _sanitize_command,
    _detect_cwd,
    _shell_exec,
    _safe_dispatch,
    ALLOWED_COMMANDS
)
from tools.cli_ops.patterns import _match_pattern
from tools.cli_ops import router


@tool
def cli(command: str, trace_id: str = "") -> str:
    """
    Natural-language command dispatcher.
    """
    def _cli_logic():
        # 🔴 Cancellation Guard: Abort before executing shell commands or LLM routing
        from core.cancellation import ensure_not_cancelled
        ensure_not_cancelled()

        # Sanitize input first
        try:
            command_inner = _sanitize_command(command)
        except ValueError as e:
            return f"Invalid command: {e}"

        # Layer 1: Pattern matching (zero tokens)
        result = _match_pattern(command_inner)
        if result is not None:
            tool_name, action, params = result
            return _safe_dispatch(tool_name, action, params)

        # Layer 2: Shell whitelist (zero tokens)
        try:
            base_cmd = shlex.split(command_inner, posix=(os.name != 'nt'))[0].lower()
            if base_cmd.endswith(".exe"):
                base_cmd = base_cmd[:-4]
                
            if base_cmd in ALLOWED_COMMANDS:
                return _shell_exec(command_inner)
        except Exception:
            pass  # Fall through to Router if parsing fails

        # Layer 3: Router dispatch
        result = router._call_router(command_inner)
        if result is not None:
            if result.get("route") == "dispatch":
                return _safe_dispatch(
                    result.get("tool_name", ""),
                    result.get("action", ""),
                    result.get("params", {})
                )

        # Layer 4: Executor escalation
        if result is not None and result.get("route") == "escalate":
            return f"Escalated to Executor: {result.get('reason', 'complex task')}"

        # Fallback: try direct dispatch with common defaults
        return _safe_dispatch("system", "help", {})

    final_result = _cli_logic()
    from core.memory_backend.pruner import prune_text
    return prune_text("cli", final_result, trace_id)