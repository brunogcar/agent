"""File writing node."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from filelock import FileLock, Timeout

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.helpers import _files_context, _get_autocode_run_path, _cleanup_old_autocode_runs
from core.config import cfg
from core.tracer import tracer

def node_write_files(state: AutocodeState) -> dict:
    """
    Write generated code to agent root.
    Handles both patch format (str_replace) and full file writes.
    Patches are preferred -- faster, cheaper, less error-prone.
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return {} # LangGraph partial update: no changes needed
    # [FIX] Schema drift: execute/debug nodes write to tdd_source_code, not generated_code
    if not state.get("tdd_source_code"):
        return {} # LangGraph partial update: no changes needed
    try:
        data = json.loads(state["tdd_source_code"])
    except Exception as e:
        tracer.step(tid, "write_files", f"JSON parse failed: {e}")
        # [P1 #9] Was: return {} (no status — workflow continues silently).
        # Now returns error status so downstream nodes know write_files failed.
        return {"status": "error", "error": f"write_files JSON parse failed: {e}"}

    from workflows.autocode_impl.patch import apply_patch

    # -- Apply str_replace patches for existing files -------------------------
    patches = data.get("patches", [])
    patch_errors = []
    for p in patches:
        rel_path = p.get("path", "")
        old_text = p.get("old", "")
        new_text = p.get("new", "")

        # Use project_root from state if available, otherwise workspace_root
        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
        target = base_path / rel_path

        if cfg.is_protected(target):
            tracer.step(tid, "write_files", f"BLOCKED protected: {rel_path}")
            continue

        if not target.exists():
            tracer.step(tid, "write_files",
                f"patch target missing, skipping: {rel_path}")
            patch_errors.append(f"{rel_path}: file not found for patch")
            continue

        result = apply_patch(target, old_text, new_text)
        if result.ok:
            tracer.step(tid, "write_files",
                f"patched {rel_path} ({result.lines_changed} lines changed)")
        else:
            tracer.step(tid, "write_files",
                f"patch FAILED {rel_path}: {result.error}")
            patch_errors.append(f"{rel_path}: {result.error}")

    # -- Write new / overwrite files ------------------------------------------
    new_files = data.get("new_files", {})
    # Backwards compat: if no patches/new_files keys, treat whole data as files dict
    if not patches and not new_files and isinstance(data, dict):
        new_files = data

    for rel_path, content in new_files.items():
        # Use project_root from state if available, otherwise workspace_root
        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
        target = base_path / rel_path

        if cfg.is_protected(target):
            tracer.step(tid, "write_files", f"BLOCKED protected: {rel_path}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = str(target) + ".lock"

        # [Bug #1] Atomic write — no .bak backup (violates project rules).
        # [P2 #13] Added 1 retry on lock timeout — was no retry, silently skipped.
        import tempfile
        import os
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
                    tracer.step(tid, "write_files",
                        f"wrote {rel_path} ({len(content)} chars)")
                break  # Success — exit retry loop
            except Timeout:
                if _attempt == 0:
                    tracer.step(tid, "write_files", f"lock timeout (retrying): {rel_path}")
                    continue  # Retry
                tracer.step(tid, "write_files", f"lock timeout (giving up): {rel_path}")
            except Exception as e:
                if 'tmp_path' in locals() and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                tracer.step(tid, "write_files", f"write error {rel_path}: {e}")
                break  # Non-timeout error — don't retry

    if patch_errors:
        tracer.step(tid, "write_files",
            f"{len(patch_errors)} patch error(s): {patch_errors[0]}")

    # On-demand cleanup of old autocode runs
    _cleanup_old_autocode_runs()

    # Build partial update dict
    updates = {}
    if patch_errors:
        updates["patch_errors"] = patch_errors

    # [Bug #3] Populate files_map for analyze_impact node.
    # Snapshot modified files (content + md5) so analyze_impact can detect
    # changes and run targeted tests. Without this, files_map is always {}
    # and impact analysis never runs.
    import hashlib
    files_map = {}
    all_modified = list(new_files.keys()) + [p.get("path", "") for p in patches if p.get("path")]
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
    if files_map:
        updates["files_map"] = files_map

    # Persist test file to per-run autocode folder
    if state.get("test_code"):
        run_dir = _get_autocode_run_path(tid)
        test_file = run_dir / "test_autocode_feature.py"
        lock_path = str(test_file) + ".lock"
        try:
            with FileLock(lock_path, timeout=10):
                test_code = state["test_code"]
                if isinstance(test_code, list):
                    test_code = "\n\n".join(test_code)
                test_file.write_text(test_code, encoding="utf-8")
                tracer.step(tid, "write_files", f"test file persisted to {test_file}")
        except Timeout:
            tracer.step(tid, "write_files", "lock timeout on test file")
        except Exception as e:
            tracer.step(tid, "write_files", f"test file write error: {e}")

        # Persist generated code for record-keeping
        if state.get("tdd_source_code"):
            try:
                gen_file = run_dir / "generated_code.json"
                gen_file.write_text(state["tdd_source_code"], encoding="utf-8")
                tracer.step(tid, "write_files", f"generated code persisted to {gen_file}")
            except Exception as e:
                tracer.step(tid, "write_files", f"generated code write error: {e}")

        # Persist debug log if present
        if state.get("debug_notes") or state.get("root_cause"):
            try:
                debug_file = run_dir / "debug_log.json"
                debug_data = {
                    "debug_notes": state.get("debug_notes", ""),
                    "root_cause": state.get("root_cause", ""),
                    "defense_notes": state.get("defense_notes", ""),
                    "tdd_iteration": state.get("tdd_iteration", 0),
                }
                debug_file.write_text(json.dumps(debug_data, indent=2), encoding="utf-8")
                tracer.step(tid, "write_files", f"debug log persisted to {debug_file}")
            except Exception as e:
                tracer.step(tid, "write_files", f"debug log write error: {e}")

        rel_path = test_file.relative_to(cfg.workspace_root)
        updates["test_files"] = [str(rel_path).replace("\\", "/")]
        updates["autocode_run_path"] = str(run_dir)

    return updates

def node_write_files_with_flag_reset(state: AutocodeState) -> dict:
    """Write files and reset retry flags."""
    # Call the main node and capture its partial updates
    updates = node_write_files(state)
    # Add the flag reset to the updates dict
    updates["step_attempt"] = 0
    return updates
