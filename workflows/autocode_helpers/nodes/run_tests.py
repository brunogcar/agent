"""
Test execution node.
"""

from __future__ import annotations
from typing import Any
from workflows.autocode_helpers.state import AutocodeState
from workflows.autocode_helpers.test_runner import run_tests_on_disk
from workflows.autocode_helpers.helpers import _files_context
from core.config import cfg
from core.tracer import tracer
import json

def node_run_tests(state: AutocodeState) -> AutocodeState:
    """Run tests on disk with real pytest. Exit code is ground truth."""
    tid = state.get("trace_id", "")
    if not state.get("generated_code"):
        return {**state, "test_result": "", "error_log": ""}

    tracer.step(tid, "run_tests", "running pytest on disk")

    try:
        files = json.loads(state["generated_code"])
    except Exception as e:
        return {**state, "error_log": f"Cannot parse generated code: {e}"}

    if not state.get("test_code"):
        return {**state, "test_result": "(no tests)", "error_log": ""}

    passed, output = run_tests_on_disk(
        files=files,
        test_code=state["test_code"],
        workspace=cfg.workspace_root,
    )

    if passed:
        tracer.step(tid, "run_tests", "PASSED")
        # Advance step counter on pass -- prevents infinite test loops
        new_step = state.get("current_step", 0) + 1
        return {**state,
                "test_result": output,
                "error_log":   "",
                "current_step": new_step}
    else:
        tracer.step(tid, "run_tests", f"FAILED: {output[:80]}")
        return {**state, "test_result": output, "error_log": output}