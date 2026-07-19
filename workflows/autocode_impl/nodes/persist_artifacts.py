"""[v2.0] Persist artifacts node — writes test file, generated code, debug log.

Split from node_write_files (Phase 3.1). This node persists artifacts to
the per-run autocode folder for debugging and traceability:
  - test_autocode_feature.py (from state["test_code"])
  - generated_code.json (from the tdd sub-state's source_code field — read
    via _get_tdd accessor)
  - debug_log.json (from debug sub-state fields, if present)

Also sets `test_files` + `autocode_run_path` in state for downstream nodes
(verify node uses these to find the test files).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from filelock import FileLock, Timeout

from workflows.autocode_impl.state import AutocodeState, _get_debug, _get_tdd  # [v2.5+v3.0] accessors
from workflows.autocode_impl.helpers import _get_autocode_run_path, _should_skip_node
from core.config import cfg
from core.tracer import tracer


def node_persist_artifacts(state: AutocodeState) -> dict:
    """[v2.0] Persist test file, generated code, and debug log to run_dir.

    Reads `test_code` from state, writes it to the per-run autocode folder.
    Also persists generated code + debug log if present.

    Returns partial state update with:
      - test_files: list of test file paths (relative to workspace_root)
      - autocode_run_path: path to the per-run folder
    """
    tid = state.get("trace_id", "")
    if _should_skip_node(state):
        return {}

    # [#47] Dry-run: skip persistence
    if state.get("dry_run"):
        return {}

    if not state.get("test_code"):
        return {}

    run_dir = _get_autocode_run_path(tid)
    test_file = run_dir / "test_autocode_feature.py"
    lock_path = str(test_file) + ".lock"

    try:
        with FileLock(lock_path, timeout=10):
            test_code = state["test_code"]
            if isinstance(test_code, list):
                test_code = "\n\n".join(test_code)
            test_file.write_text(test_code, encoding="utf-8")
            tracer.step(tid, "persist_artifacts", f"test file persisted to {test_file}")
    except Timeout:
        tracer.step(tid, "persist_artifacts", "lock timeout on test file")
    except Exception as e:
        tracer.step(tid, "persist_artifacts", f"test file write error: {e}")

    # Persist generated code for record-keeping
    source_code = _get_tdd(state, "source_code", "")  # [v3.0] accessor (was flat field)
    if source_code:
        try:
            gen_file = run_dir / "generated_code.json"
            gen_file.write_text(source_code, encoding="utf-8")
            tracer.step(tid, "persist_artifacts", f"generated code persisted to {gen_file}")
        except Exception as e:
            tracer.step(tid, "persist_artifacts", f"generated code write error: {e}")

    # Persist debug log if present
    # [v2.5] Use _get_debug accessors (read sub-state first, fall back to flat)
    debug_notes = _get_debug(state, "notes", "")
    root_cause = _get_debug(state, "root_cause", "")
    if debug_notes or root_cause:
        try:
            debug_file = run_dir / "debug_log.json"
            debug_data = {
                "debug_notes": debug_notes,
                "root_cause": root_cause,
                "defense_notes": _get_debug(state, "defense_notes", ""),
                "tdd_iteration": _get_tdd(state, "iteration", 0),  # [v3.0] accessor (was flat field)
            }
            debug_file.write_text(json.dumps(debug_data, indent=2), encoding="utf-8")
            tracer.step(tid, "persist_artifacts", f"debug log persisted to {debug_file}")
        except Exception as e:
            tracer.step(tid, "persist_artifacts", f"debug log write error: {e}")

    rel_path = test_file.relative_to(cfg.workspace_root)
    return {
        "test_files": [str(rel_path).replace("\\", "/")],
        "autocode_run_path": str(run_dir),
    }
