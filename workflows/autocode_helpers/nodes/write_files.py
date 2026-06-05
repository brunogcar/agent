"""
File writing node.
"""

from __future__ import annotations

import json
import shutil

from pathlib import Path
from typing import Any
from filelock import FileLock, Timeout

from workflows.autocode_helpers.state import AutocodeState
from workflows.autocode_helpers.helpers import _files_context
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
        return {}  # LangGraph partial update: no changes needed
    # [FIX] Schema drift: execute/debug nodes write to tdd_source_code, not generated_code
    if not state.get("tdd_source_code"):
        return {}  # LangGraph partial update: no changes needed
    try:
        data = json.loads(state["tdd_source_code"])
    except Exception as e:
        tracer.step(tid, "write_files", f"JSON parse failed: {e}")
        return {}  # LangGraph partial update: no changes needed

    from workflows.autocode_helpers.patch import apply_patch

    # -- Apply str_replace patches for existing files -------------------------
    patches      = data.get("patches", [])
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
        bak_path  = target.with_suffix(target.suffix + ".bak")

        try:
            with FileLock(lock_path, timeout=10):
                if target.exists():
                    shutil.copy2(target, bak_path)
                target.write_text(str(content), encoding="utf-8")
            tracer.step(tid, "write_files",
                        f"wrote {rel_path} ({len(content)} chars)")
        except Timeout:
            tracer.step(tid, "write_files", f"lock timeout: {rel_path}")
        except Exception as e:
            tracer.step(tid, "write_files", f"write error {rel_path}: {e}")

    if patch_errors:
        tracer.step(tid, "write_files",
                    f"{len(patch_errors)} patch error(s): {patch_errors[0]}")

    # Persist test file to agent root so verify can find it
    if state.get("test_code"):
        # Use project_root from state if available, otherwise workspace_root
        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
        test_file = base_path / "autocode" / "test_autocode_feature.py"
        lock_path = str(test_file) + ".lock"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(lock_path, timeout=10):
                test_code = state["test_code"]
                if isinstance(test_code, list):
                    test_code = "\n\n".join(test_code)
                test_file.write_text(test_code, encoding="utf-8")
            tracer.step(tid, "write_files", "test file persisted")
        except Timeout:
            tracer.step(tid, "write_files", "lock timeout on test file")
        except Exception as e:
            tracer.step(tid, "write_files", f"test file write error: {e}")

    # Build partial update dict
    updates = {}
    if patch_errors:
        updates["patch_errors"] = patch_errors
    if state.get("test_code"):
        updates["test_files"] = ["autocode/test_autocode_feature.py"]
    return updates

def node_write_files_with_flag_reset(state: AutocodeState) -> dict:
    """Write files and reset retry flags."""
    # Call the main node and capture its partial updates
    updates = node_write_files(state)
    # Add the flag reset to the updates dict
    updates["step_attempt"] = 0
    return updates