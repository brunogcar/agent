"""workflows/autocode.py — Thin facade for the autocode workflow.

v1.1.2: Added structured artifacts (#44), multi-file git-diff input (#46),
and dry-run guards (#47, in the mutation nodes). Backward-compat shim
delegates to base.py's run_workflow().

[BACKWARD COMPAT] run_autocode_agent() is kept as a thin shim that delegates
to run_workflow(workflow_type="autocode"). This preserves the public API.
TODO (roadmap #34): audit callers and remove the shim once all use
run_workflow() directly.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

# Graph + metadata (the facade's real job)
from workflows.autocode_impl.graph import build_graph, get_graph, WORKFLOW_METADATA

# State (public API — used by tests and callers)
from workflows.autocode_impl.state import AutocodeState, _default_state

__all__ = [
    "run_autocode_agent",
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
        "commit_sha": final_state.get("commit_sha", ""),
        "branch_name": final_state.get("branch_name", ""),
        "modified_files": final_state.get("modified_files", []),
        "test_results": final_state.get("test_results", {}),
        "tdd_status": final_state.get("tdd_status", ""),
        "tdd_iteration": final_state.get("tdd_iteration", 0),
        "verification_passed": final_state.get("verification_passed", False),
        "skill_created": final_state.get("skill_created", False),
        "skill_path": final_state.get("skill_path", ""),
    }


def run_autocode_agent(
    task: str,
    files: dict[str, str] | None = None,
    mode: str = "feature",
    target_file: str = "",
    dry_run: bool = False,
    trace_id: str = "",
    git_diff: bool = False,
) -> dict[str, Any]:
    """Run the autocode workflow.

    [v1.1] Backward-compat shim — delegates to base.py's run_workflow().
    This gets checkpoint/resume, tracing, and timeout for free.

    [v1.1.2] Added:
      - #44: structured artifacts in the return dict (``artifacts`` key)
      - #46: ``git_diff=True`` + ``files={"all changed": ""}`` resolves changed
        files via ``git diff --name-only`` so callers don't paste every path.
      - #47: ``dry_run=True`` now actually skips mutations (write_files, commit,
        branch creation all check the flag).

    Args:
        task: The task description.
        files: Dictionary of file paths to content. Use the special key
            ``"all changed"`` with ``git_diff=True`` to auto-resolve changed files.
        mode: Task mode (feature, fix, refactor, edit, create_skill, audit).
        target_file: The target file for the operation.
        dry_run: If True, skip all mutations (file writes, git commits, branches).
        trace_id: Optional trace ID (created if empty).
        git_diff: If True, resolve ``files["all changed"]`` via ``git diff``.

    Returns:
        Dict with status, result, trace_id, commit_sha, error, and
        ``artifacts`` (structured #44 dict).
    """
    from workflows.base import run_workflow

    # [#46] Preprocess files input (resolve "all changed" via git diff)
    resolved_files = _resolve_files_input(files, git_diff=git_diff)

    result = run_workflow(
        workflow_type="autocode",
        goal=task,
        task=task,
        files=resolved_files,
        mode=mode,
        target_file=target_file,
        dry_run=dry_run,
        trace_id=trace_id,
    )

    # [#44] Attach structured artifacts. run_workflow returns the final state
    # merged with the dispatcher's status/result/error keys. We shape the
    # autocode-specific fields into a typed artifacts dict.
    result["artifacts"] = _shape_artifacts(result)

    return result
