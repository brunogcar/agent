"""workflows/autocode.py — Thin facade for the autocode workflow.

v1.1.2: Added structured artifacts (#44), multi-file git-diff input (#46),
and dry-run guards (#47, in the mutation nodes).

[v1.2] run_autocode_agent() shim removed — use run_workflow("autocode") directly.
Callers wanting structured artifacts must call _shape_artifacts() on the
run_workflow() return value themselves.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

# Graph + metadata (the facade's real job)
from workflows.autocode_impl.graph import build_graph, get_graph, WORKFLOW_METADATA

# State (public API — used by tests and callers)
from workflows.autocode_impl.state import (
    AutocodeState,
    _default_state,
    _get_vcs,
    _get_files,
    _get_tdd,
    _get_verify,
)

__all__ = [
    "build_graph",
    "get_graph",
    "WORKFLOW_METADATA",
    "AutocodeState",
    "_default_state",
]


def _resolve_files_input(files: dict[str, str] | None, git_diff: bool = False) -> dict[str, str]:
    """[#46] Preprocess the files input.

    Supports a special key ``"all changed"`` (when git_diff=True) that reads
    ``git diff --name-only`` from the current project and loads each file's
    content. This lets callers say "fix the files I just changed" without
    pasting every file path.

    Args:
        files: The files dict from the caller. May contain the special
            key "all changed" to trigger git-diff resolution.
        git_diff: If True, resolve the "all changed" key via git diff.

    Returns:
        A files dict with all keys resolved to {path: content}.
    """
    if not files:
        return {}

    if not git_diff or "all changed" not in files:
        # No git-diff resolution needed — return as-is (minus the special key
        # if someone passed it without git_diff=True).
        return {k: v for k, v in files.items() if k != "all changed"}

    # [#46] Resolve "all changed" via git diff --name-only
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            # Fall back to staged + unstaged if HEAD comparison fails (e.g. new repo)
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        changed = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    except Exception:
        changed = []

    resolved = {}
    for path in changed:
        p = Path(path)
        if p.exists() and p.is_file():
            try:
                resolved[path] = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass  # Skip unreadable files

    # Merge in any explicitly-passed files (besides the special key)
    for k, v in files.items():
        if k != "all changed":
            resolved[k] = v

    return resolved


def _shape_artifacts(final_state: dict) -> dict[str, Any]:
    """[#44] Shape the final state into a structured artifacts dict.

    Makes the output machine-consumable: callers get a typed dict with
    commit_sha, branch_name, modified_files, test_results, etc. instead of
    having to guess which state keys to read.
    """
    return {
        "commit_sha": _get_vcs(final_state, "commit_sha", ""),  # [v3.0] accessor
        "branch_name": _get_vcs(final_state, "branch", ""),  # [v3.0] accessor (was flat branch_name + branch fallback)
        "modified_files": _get_files(final_state, "modified_files", []),  # [v3.0] accessor
        "test_results": final_state.get("test_results", {}),  # [v3.0] stays flat (ephemeral)
        "tdd_status": _get_tdd(final_state, "status", ""),  # [v3.0] accessor
        "tdd_iteration": _get_tdd(final_state, "iteration", 0),  # [v3.0] accessor
        "verification_passed": _get_verify(final_state, "passed", False),  # [v3.0] accessor
        "skill_created": final_state.get("skill_created", False),
        "skill_path": final_state.get("skill_path", ""),
    }
