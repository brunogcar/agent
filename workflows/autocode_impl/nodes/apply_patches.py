"""[v2.0] Apply patches node — handles str_replace patches only.

Split from node_write_files (Phase 3.1). This node applies patches to existing
files. New file writes + artifact persistence are handled by separate nodes:
  - node_write_new_files (next in graph)
  - node_persist_artifacts (after write_new_files)

The _is_path_safe() helper is shared across all write nodes — defined here
and imported by node_write_new_files.

[v1.2] Removed unused `import json` (no `json.` calls in the body — only
`_parse_json` from helpers is used).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from workflows.autocode_impl.state import AutocodeState, _get_files, _get_tdd  # [v2.3+v3.0] accessors
from workflows.autocode_impl.helpers import _parse_json, _should_skip_node
from core.config import cfg
from core.tracer import tracer


def _is_path_safe(base_path: Path, rel_path: str) -> bool:
    """[Pre-2.0 Fix] Verify that a resolved path is strictly within base_path.

    Prevents path traversal attacks where the LLM generates rel_path like
    "../../etc/passwd" or "../../../Windows/System32/malicious.exe".

    Shared across node_apply_patches + node_write_new_files.
    """
    if not rel_path or not isinstance(rel_path, str):
        return False
    try:
        target = (base_path / rel_path).resolve()
        base_resolved = base_path.resolve()
        if hasattr(target, 'is_relative_to'):
            return target.is_relative_to(base_resolved)
        return str(target).startswith(str(base_resolved))
    except (ValueError, RuntimeError):
        return False


def node_apply_patches(state: AutocodeState) -> dict:
    """[v2.0] Apply str_replace patches to existing files.

    Reads `tdd_source_code` from state, extracts `patches` array, applies
    each patch via apply_patch(). Builds `modified_files` list for downstream
    impact analysis.

    Returns partial state update with:
      - modified_files: list of paths that were patched
      - patch_errors: list of error messages (if any)
      - status: "error" if JSON parse fails, "dry_run" if dry_run
    """
    tid = state.get("trace_id", "")
    if _should_skip_node(state):
        return {}

    if not _get_tdd(state, "source_code", ""):  # [v3.0] accessor (was flat field)
        return {}

    # Parse the generated code JSON (shared parsing — patches + new_files)
    # [Hardening P1.4] Use _parse_json (handles markdown-fenced JSON) instead of raw json.loads.
    # _parse_json returns {} on failure; convert empty result into an explicit error
    # so the existing `except Exception` handler + downstream callers see the failure.
    try:
        data = _parse_json(_get_tdd(state, "source_code", ""))  # [v3.0] accessor (was flat field)
        if not data:
            raise ValueError("_parse_json returned empty dict (invalid or unparseable JSON)")
    except Exception as e:
        tracer.step(tid, "apply_patches", f"JSON parse failed: {e}")
        return {"status": "error", "error": f"apply_patches JSON parse failed: {e}"}

    from workflows.autocode_impl.patch import apply_patch

    patches = data.get("patches", [])
    patch_errors = []
    modified_files = []

    base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root

    # [v1.4 P0] Validation loop runs for BOTH dry_run and normal paths.
    # Path traversal, protected file, and file-exists checks must run even in
    # dry_run so callers learn about malformed patches before applying them.
    for p in patches:
        rel_path = p.get("path", "")
        old_text = p.get("old", "")
        new_text = p.get("new", "")

        target = base_path / rel_path

        # [Pre-2.0 Fix] Path traversal guard
        if not _is_path_safe(base_path, rel_path):
            tracer.step(tid, "apply_patches", f"BLOCKED path traversal: {rel_path}")
            patch_errors.append(f"{rel_path}: path traversal blocked")
            continue

        if cfg.is_protected(target):
            tracer.step(tid, "apply_patches", f"BLOCKED protected: {rel_path}")
            continue

        if not target.exists():
            tracer.step(tid, "apply_patches", f"patch target missing, skipping: {rel_path}")
            patch_errors.append(f"{rel_path}: file not found for patch")
            continue

        # [v1.4 P0] Skip actual apply_patch() in dry_run — validation already done above.
        if state.get("dry_run"):
            continue

        result = apply_patch(target, old_text, new_text)
        if result.ok:
            tracer.step(tid, "apply_patches", f"patched {rel_path} ({result.lines_changed} lines changed)")
            modified_files.append(rel_path)
        else:
            tracer.step(tid, "apply_patches", f"patch FAILED {rel_path}: {result.error}")
            patch_errors.append(f"{rel_path}: {result.error}")

    if patch_errors:
        tracer.step(tid, "apply_patches", f"{len(patch_errors)} patch error(s): {patch_errors[0]}")

    # [#47] Dry-run: skip all file writes AFTER validation checks pass.
    # [v1.4 P0] Moved dry_run check to AFTER validation loop so path traversal,
    # protected file, and file-exists checks still run in dry_run mode.
    if state.get("dry_run"):
        tracer.step(tid, "apply_patches", "dry_run=True — skipping patch application")
        # [v2.3] RMW: write to files sub-state
        current_files = dict(state.get("files_state", {}))
        current_files["modified_files"] = []
        updates: dict[str, Any] = {"status": "dry_run", "files_state": current_files}
        if patch_errors:
            updates["patch_errors"] = patch_errors
        return updates

    # [v2.3] RMW: write to files sub-state
    current_files = dict(state.get("files_state", {}))
    current_files["modified_files"] = modified_files
    updates = {"files_state": current_files}
    if patch_errors:
        updates["patch_errors"] = patch_errors
    return updates
