"""[v2.0] Apply patches node — handles str_replace patches only.

Split from node_write_files (Phase 3.1). This node applies patches to existing
files. New file writes + artifact persistence are handled by separate nodes:
  - node_write_new_files (next in graph)
  - node_persist_artifacts (after write_new_files)

The _is_path_safe() helper is shared across all write nodes — defined here
and imported by node_write_new_files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflows.autocode_impl.state import AutocodeState
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
    if state.get("status") in ("needs_clarification", "failed"):
        return {}

    if not state.get("tdd_source_code"):
        return {}

    # Parse the generated code JSON (shared parsing — patches + new_files)
    try:
        data = json.loads(state["tdd_source_code"])
    except Exception as e:
        tracer.step(tid, "apply_patches", f"JSON parse failed: {e}")
        return {"status": "error", "error": f"apply_patches JSON parse failed: {e}"}

    # [#47] Dry-run: skip all file writes AFTER validation checks pass.
    if state.get("dry_run"):
        tracer.step(tid, "apply_patches", "dry_run=True — skipping patch application")
        return {"status": "dry_run", "modified_files": []}

    from workflows.autocode_impl.patch import apply_patch

    patches = data.get("patches", [])
    patch_errors = []
    modified_files = []

    for p in patches:
        rel_path = p.get("path", "")
        old_text = p.get("old", "")
        new_text = p.get("new", "")

        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
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

        result = apply_patch(target, old_text, new_text)
        if result.ok:
            tracer.step(tid, "apply_patches", f"patched {rel_path} ({result.lines_changed} lines changed)")
            modified_files.append(rel_path)
        else:
            tracer.step(tid, "apply_patches", f"patch FAILED {rel_path}: {result.error}")
            patch_errors.append(f"{rel_path}: {result.error}")

    if patch_errors:
        tracer.step(tid, "apply_patches", f"{len(patch_errors)} patch error(s): {patch_errors[0]}")

    updates: dict[str, Any] = {"modified_files": modified_files}
    if patch_errors:
        updates["patch_errors"] = patch_errors
    return updates
