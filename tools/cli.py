"""CLI meta-tool — natural-language command dispatcher.

Architecture (4 layers):
 1. Pattern match — regex, zero tokens, instant
 2. Shell whitelist — subprocess, zero tokens, real OS output
 3. Router — LLM decides: direct dispatch or escalate
 4. Executor — complex tasks handed to planner/executor workflow

All proxy actions auto-register via @register_action in cli_ops/actions/*.py.
The facade coordinates the 4 layers and applies security controls:
 - Input sanitization (_sanitize_command)
 - Path guard integration (core.path_guard)
 - Cancellation guard (ensure_not_cancelled)
 - Trace propagation (trace_id)

NOTE: CLI differs from git/file tools in how @meta_tool is applied:
 - git/file: facade takes action: str → @meta_tool patches to Literal[...]
 - cli: facade takes command: str (natural language) → @meta_tool skips
 the Literal patch (no "action" in annotations) but still generates
 docstring and __tool_metadata__ from DISPATCH metadata. This is
 intentional — CLI is a meta-tool that routes natural language, not
 a direct action dispatcher.

IMPORT ORDER CRITICAL:
 cli_ops/__init__.py must import all action modules BEFORE cli.py
 is imported. This ensures DISPATCH is populated for @meta_tool.
 If DISPATCH is empty, @meta_tool raises ValueError at import time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import cfg
from tools._meta_tool import meta_tool
from tools.cli_ops._registry import DISPATCH
from tools.cli_ops.helpers import (
    _sanitize_command,
    _shell_exec,
    _safe_dispatch,
)
from tools.cli_ops.patterns import _match_pattern
from tools.cli_ops.router import _call_router

# @meta_tool expects a flat dict of {action_name: {func, help, examples}}.
# But CLI's DISPATCH is nested by tool namespace: {tool: {action: {func, help, examples}}}.
# Proxy actions register to their own namespace ("system", "file", "git", etc.)
# not "cli". So we flatten all namespaces into a synthetic "cli" dispatch
# for docstring/metadata generation. This lets the LLM see all available
# proxy actions when deciding how to use the CLI tool.
#
# NOTE: If two namespaces define the same action name (e.g., git:log and
# lms:log), the last one wins in the flattened dict. This affects the
# @meta_tool docstring only — runtime dispatch uses the full namespace.
# Currently git:log and lms:log both exist; lms:log wins in docstring.
# This is acceptable since the docstring is reference, not schema.
_CLI_META_DISPATCH = {}
for _tool_actions in DISPATCH.values():
    _CLI_META_DISPATCH.update(_tool_actions)


def _ok(output: str, trace_id: str = "") -> dict[str, Any]:
    """Format successful response dict.

    NOTE: Always returns status="success" even when the routed action
    fails. The failure is in the output string. This is intentional —
    CLI is human-facing. Callers inspect the output text, not the status.
    """
    return {
        "status": "success",
        "output": output,
        "trace_id": trace_id,
    }


def _ensure_not_cancelled(trace_id: str) -> None:
    """Check if the current trace has been cancelled.

    Tries to import from core.runtime.cancellation, falls back to no-op
    if unavailable. This avoids hard dependency on tracer for tests.
    """
    try:
        from core.runtime.cancellation import ensure_not_cancelled as _enc
        _enc(trace_id)
    except (ImportError, AttributeError):
        pass


@meta_tool(
    _CLI_META_DISPATCH,
    doc_sections=[
        "4-Layer Dispatch Architecture:",
        " 1. Pattern match — regex for common commands (zero tokens)",
        " 2. Shell whitelist — safe subprocess execution (zero tokens)",
        " 3. Router — LLM classifies ambiguous commands",
        " 4. Executor — complex tasks escalated to planner workflow",
        "",
        "Security:",
        " - shell=False prevents command chaining",
        " - ALLOWED_COMMANDS whitelist controls binaries",
        " - BLOCKED_FLAGS prevents arbitrary code execution",
        " - core.path_guard validates all filesystem paths",
        "",
        "Proxy Actions:",
        " Each action routes to a specific tool (file, git, web, etc.)",
        " and formats the result for human-readable output.",
    ],
)
def cli(command: str = "", trace_id: str = "") -> dict[str, Any]:
    """Execute a natural-language CLI command through the 4-layer dispatch.

    Args:
        command: Natural-language command string (e.g., "git status",
            "read file.py", "search python tutorials").
        trace_id: Execution trace identifier for observability.

    Returns:
        dict with status, output, and trace_id.
        NOTE: status is always "success" — inspect output for errors.
    """
    # Layer 0: Sanitize and validate
    command_inner = _sanitize_command(command)
    _ensure_not_cancelled(trace_id)

    # Layer 1: Pattern match (zero tokens, instant)
    match = _match_pattern(command_inner)
    if match:
        tool_name, action, params = match
        params["trace_id"] = trace_id
        result = _safe_dispatch(tool_name, action, params)
        return _ok(result, trace_id=trace_id)

    # Layer 2: Shell whitelist (subprocess, zero tokens)
    shell_result = _shell_exec(command_inner)
    if not shell_result.startswith("Shell error"):
        return _ok(shell_result, trace_id=trace_id)

    # Layer 3: Router (LLM decides)
    result = _call_router(command_inner)
    if result and result.get("route") == "dispatch":
        tool_name = result.get("tool_name", "")
        action = result.get("action", "")
        params = result.get("params", {})
        params["trace_id"] = trace_id
        result = _safe_dispatch(tool_name, action, params)
        return _ok(result, trace_id=trace_id)

    # Layer 4: Executor escalation
    reason = result.get("reason", "complex task") if result else "no router response"
    return _ok(f"Escalated to Executor: {reason}", trace_id=trace_id)
