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

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Docstring Builder
# Preserves the exact LLM-facing documentation format from the original.
# Reads help text and examples directly from the registered operations.
# ─────────────────────────────────────────────────────────────────────────────
def _build_doc() -> str:
    """
    Generate the tool's docstring dynamically from registered git operations.
    This ensures that any new operation added via @register_action automatically
    appears in the LLM's tool description without manual updates.
    """
    git_ops = DISPATCH.get("git", {})
    lines = [
        "Git version control operations.",
        "",
        "operation:  " + " | ".join(sorted(git_ops.keys())),
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
        lines.append(" ")
        exs = info.get("examples", [])
        if exs:
            lines.append("  Examples:")
            for ex in exs:
                lines.append(f"    {ex}")
            lines.append(" ")

    # Common usage patterns (kept as a quick reference for the LLM)
    lines.append("Common usage patterns:")
    lines.append("    git(operation=\"status\")                  # check working tree")
    lines.append("    git(operation=\"log\", n=5)                # recent commits")
    lines.append("    git(operation=\"snapshot\", message=\"...\") # safe point before changes")
    lines.append("    git(operation=\"commit\", message=\"...\")  # after a successful change")
    lines.append("    git(operation=\"rollback\")                # undo uncommitted changes")
    
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher Implementation
# Preserves exact parameter signature, root resolution, repo validation,
# and error handling from the original implementation.
# ─────────────────────────────────────────────────────────────────────────────
@tool
def git(
    operation: str,
    message:   str  = "",
    root:      str  = "agent",
    n:         int  = 10,
    path:      str  = "",
    force:     bool = False,
) -> dict:
    """
    Git version control operations. Dispatched via standardized registry.
    Preserves original safety checks, backward-compat aliases, and LLM docstrings.
    """
    operation = operation.strip().lower()

    # 1. Resolve working directory (preserves backward-compat alias logic)
    cwd, err = _resolve_root(root, path)
    if err:
        return {"status": "error", "error": err}

    # 2. Lookup operation in registry
    git_ops = DISPATCH.get("git", {})
    op_info = git_ops.get(operation)
    if not op_info:
        return {
            "status": "error",
            "error": f"Unknown operation '{operation}'. Valid: {' | '.join(sorted(git_ops.keys()))}",
        }

    # 3. Validate repository if the operation requires it
    if op_info.get("needs_repo"):
        ok, err = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err}

    # 4. Prepare kwargs exactly as original handlers expect
    kwargs = {
        "cwd": cwd,
        "message": message,
        "path": path,
        "n": n,
        "force": force,
    }

    # 5. Execute handler safely
    try:
        return op_info["func"](**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Attach dynamic docstring so MCP/LLM sees the formatted help text
git.__doc__ = _build_doc()

# ---------------------------------------------------------------------------
# Commands intentionally excluded from the git meta‑tool
# ---------------------------------------------------------------------------
#
# The following operations are NOT exposed to the autonomous agent because they
# either involve remote repositories, are destructive to shared history, or
# require human judgement for conflict resolution:
#
#   fetch       – touches a remote; can update remote‑tracking branches and
#                 potentially introduce unwanted refs. The agent runs in an
#                 isolated, local‑first environment and does not need remote
#                 awareness by default.
#
#   pull        – fetch + merge. Combines network access with automatic
#                 merging that can produce conflicts. Unsuitable for
#                 unsupervised execution.
#
#   merge       – joins two branches. May create merge conflicts that the
#                 agent cannot resolve reliably. Branch‑per‑feature with
#                 explicit commits is preferred.
#
#   rebase      – rewrites commit history. Extremely dangerous for an
#                 autonomous agent; can lose work or corrupt the timeline.
#
#   push        – sends local commits to a remote. Explicitly excluded to
#                 maintain the agent's local‑only boundary.
#
# If a future use case requires any of these (e.g., a fully‑automated CI
# pipeline), add them behind a `allow_remote=True` flag and enforce
# additional safety guards (authentication, conflict detection, etc.).