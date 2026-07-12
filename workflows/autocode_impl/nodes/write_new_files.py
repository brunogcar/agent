"""[v2.0] Write new files node — handles full file writes (atomic).

Split from node_write_files (Phase 3.1). This node writes new files or
overwrites existing ones using atomic writes (tempfile + os.replace).
Patch application is handled by node_apply_patches (previous in graph).

Also builds `files_map` for analyze_impact — snapshots all modified files
(patches + new files) so impact analysis can detect changes.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from filelock import FileLock, Timeout

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.helpers import _cleanup_old_autocode_runs, _parse_json  # [Hardening P1.4] added _parse_json
from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.nodes.apply_patches import _is_path_safe


def node_write_new_files(state: AutocodeState) -> dict:
    """[v2.0] Write new/overwrite files atomically. Build files_map for impact analysis.

    Reads `tdd_source_code` from state, extracts `new_files` dict, writes
    each file atomically (tempfile + os.replace + FileLock with 1 retry).

    Also builds `files_map` — snapshots of all modified files (from patches
    applied by node_apply_patches + new files written here) for analyze_impact.

    Returns partial state update with:
      - files_map: dict of {path: FileSnapshot} for analyze_impact
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed", "error"):
        return {}

    if not state.get("tdd_source_code"):
        return {}

    # [#47] Dry-run: skip writes
    if state.get("dry_run"):
        tracer.step(tid, "write_new_files", "dry_run=True — skipping file writes")
        return {}

    # Parse the generated code JSON
    # [Hardening P1.4] Use _parse_json (handles markdown-fenced JSON) instead of raw json.loads.
    # _parse_json returns {} on failure; treat empty result as parse failure.
    try:
        data = _parse_json(state.get("tdd_source_code", ""))
        if not data:
            tracer.step(tid, "write_new_files", "JSON parse failed: _parse_json returned empty dict")
            return {}
    except Exception as e:
        tracer.step(tid, "write_new_files", f"JSON parse failed: {e}")
        return {}

    patches = data.get("patches", [])
    new_files = data.get("new_files", {})
    # Backwards compat: if no patches/new_files keys, treat whole data as files dict
    if not patches and not new_files and isinstance(data, dict):
        new_files = data

    # -- Write new / overwrite files ------------------------------------------
    written_files = []
    for rel_path, content in new_files.items():
        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
        target = base_path / rel_path

        # [Pre-2.0 Fix] Path traversal guard
        if not _is_path_safe(base_path, rel_path):
            tracer.step(tid, "write_new_files", f"BLOCKED path traversal: {rel_path}")
            continue

        if cfg.is_protected(target):
            tracer.step(tid, "write_new_files", f"BLOCKED protected: {rel_path}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = str(target) + ".lock"

        # [Bug #1] Atomic write — no .bak backup (violates project rules).
        # [P2 #13] Added 1 retry on lock timeout.
        for _attempt in range(2):  # 1 initial + 1 retry
            try:
                with FileLock(lock_path, timeout=10):
                    with tempfile.NamedTemporaryFile(
                        mode='w', encoding='utf-8', dir=target.parent,
                        delete=False, suffix='.tmp'
                    ) as tmp:
                        tmp.write(str(content))
                        tmp_path = Path(tmp.name)
                    os.replace(tmp_path, target)
                    tracer.step(tid, "write_new_files", f"wrote {rel_path} ({len(content)} chars)")
                written_files.append(rel_path)
                break  # Success — exit retry loop
            except Timeout:
                if _attempt == 0:
                    tracer.step(tid, "write_new_files", f"lock timeout (retrying): {rel_path}")
                    continue
                tracer.step(tid, "write_new_files", f"lock timeout (giving up): {rel_path}")
            except Exception as e:
                if 'tmp_path' in locals() and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                tracer.step(tid, "write_new_files", f"write error {rel_path}: {e}")
                break  # Non-timeout error — don't retry

    # On-demand cleanup of old autocode runs
    _cleanup_old_autocode_runs()

    # [Bug #3] Build files_map for analyze_impact node.
    # Snapshot modified files (patches + new files) so analyze_impact can
    # detect changes and run targeted tests.
    files_map = {}
    modified_from_patches = [p.get("path", "") for p in patches if p.get("path")]
    all_modified = written_files + modified_from_patches
    for mod_path in all_modified:
        if not mod_path:
            continue
        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
        full_path = base_path / mod_path
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                files_map[mod_path] = {
                    "content_preview": content[:8000],
                    "preview_md5": hashlib.md5(content[:8000].encode("utf-8")).hexdigest(),
                    "full_md5": hashlib.md5(content.encode("utf-8")).hexdigest(),
                    "size": len(content),
                    "truncated": len(content) > 8000,
                }
            except Exception:
                pass

    updates: dict[str, Any] = {}
    if files_map:
        updates["files_map"] = files_map
    # [Hardening P1.8] Propagate written_files into modified_files.
    # Without this, new files written here were never reflected in modified_files,
    # so analyze_impact and downstream nodes missed them (only patched files
    # showed up). Merge with existing modified_files from apply_patches.
    if written_files:
        existing_modified = state.get("modified_files", [])
        updates["modified_files"] = list(set(existing_modified + written_files))
    return updates
