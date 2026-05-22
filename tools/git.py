"""
tools/git.py — Git meta-tool for version control operations.

The LLM sees ONE tool: git(operation, ...)
Supported operations: status, log, diff, commit, init, restore, rollback,
                      snapshot, show, tag, branch, checkout.

Default root: "agent" (the agent's own repository). Pass root="workspace" to
work on a project inside the workspace.

IMPORTANT - root vs path parameter:
  root  - the repo directory: "agent" (default) | "workspace" | "/absolute/path"
          DEFAULT is "agent" – the agent's own source code.
          Use root="workspace" for project repos.
  path  - ONLY used by diff to filter a specific file. NOT the repo directory.
          Exception: if you pass path="D:/mcp/agent" with root="workspace",
          the tool detects this and uses path as the root (backward-compat alias).

Commands intentionally excluded from autonomous execution:
  fetch, pull, merge, rebase, push
  These involve remote operations, destructive history rewrites, or conflict
  resolution, which require human judgement and are unsafe for unsupervised agents.
"""

from __future__ import annotations

from core.config import cfg
from registry import tool
from tools.git_ops._registry import DISPATCH
from tools.git_ops.helpers import _resolve_root, _check_repo
from core.path_guard import check_git_operation, make_path_error
from core.tracer import tracer

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Docstring Builder
# ─────────────────────────────────────────────────────────────────────────────
def _build_doc() -> str:
    """
    Generate the tool's docstring dynamically from registered git operations.
    """
    git_ops = DISPATCH.get("git", {})
    lines = [
        "Git version control operations.",
        "",
        "operation:   " + " | ".join(sorted(git_ops.keys())),
        "",
        "IMPORTANT - root vs path parameter:",
        "  root  - the repo directory: \"agent\" (default) | \"workspace\" | \"/absolute/path\"",
        "          DEFAULT is \"agent\" – the agent's own source code.",
        "          Use root=\"workspace\" for project repos.",
        "  path  - ONLY used by diff to filter a specific file. NOT the repo directory.",
        "          Exception: if you pass path=\"D:/mcp/agent\" with root=\"workspace\",",
        "          the tool detects this and uses path as the root (backward-compat alias).",
        "",
    ]
    for name in sorted(git_ops.keys()):
        info = git_ops[name]
        lines.append(info["help"])
        lines.append("  ")
        exs = info.get("examples", [])
        if exs:
            lines.append("  Examples: ")
            for ex in exs:
                lines.append(f"    {ex}")
            lines.append("  ")

    lines.append("Common usage patterns:")
    lines.append("    git(operation=\"status\")                  # check working tree")
    lines.append("    git(operation=\"log\", n=5)                # recent commits")
    lines.append("    git(operation=\"snapshot\", message=\"...\") # safe point before changes")
    lines.append("    git(operation=\"commit\", message=\"...\")  # after a successful change")
    lines.append("    git(operation=\"rollback\")                # undo uncommitted changes")

    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher Implementation
# ─────────────────────────────────────────────────────────────────────────────
@tool
def git(
    operation: str,
    message:   str  = "",
    root:      str  = "agent",
    n:         int  = 10,
    path:      str  = "",
    force:     bool = False,
    target:    str  = "",
    trace_id:  str  = "",
) -> dict:
    """
    Git version control operations. Dispatched via standardized registry.
    """
    operation = operation.strip().lower()
    if not trace_id:
        trace_id = tracer.new_trace("git", goal=operation)

    # 1. Resolve working directory (preserves backward-compat alias logic)
    cwd, err = _resolve_root(root, path)
    if err:
        return make_path_error(path or root, operation, err, trace_id)

    # 2. Validate git operation scoping (blocks clone outside workspace)
    allowed, err, resolved_cwd = check_git_operation(
        operation=operation,
        cwd=cwd,
        target=target if target else None
    )
    if not allowed:
        return make_path_error(cwd or path, operation, err, trace_id)

    # Use resolved_cwd if provided
    actual_cwd = resolved_cwd or cwd

    # 3. Lookup operation in registry
    git_ops = DISPATCH.get("git", {})
    op_info = git_ops.get(operation)
    if not op_info:
        return {
            "status": "error",
            "error": f"Unknown operation '{operation}'. Valid: {' | '.join(sorted(git_ops.keys()))}",
            "trace_id": trace_id,
        }

    # 4. Validate repository if the operation requires it
    if op_info.get("needs_repo"):
        ok, err = _check_repo(actual_cwd)
        if not ok:
            return {"status": "error", "error": err, "trace_id": trace_id}

    # 5. Prepare kwargs exactly as original handlers expect
    kwargs = {
        "cwd": actual_cwd,
        "message": message,
        "path": path,
        "n": n,
        "force": force,
        "trace_id": trace_id,
    }
    
    if target:
        kwargs["target"] = target

    # 6. Execute handler safely
    try:
        return op_info["func"](**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e), "trace_id": trace_id}

# Attach dynamic docstring so MCP/LLM sees the formatted help text
git.__doc__ = _build_doc()

# ---------------------------------------------------------------------------
# Commands intentionally excluded from the git meta‑tool
# ---------------------------------------------------------------------------
# The following operations are NOT exposed to the autonomous agent because they
# either involve remote repositories, are destructive to shared history, or
# require human judgement for conflict resolution:
# fetch, pull, merge, rebase, push