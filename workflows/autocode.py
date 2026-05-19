"""
autocode.py -- Superpowers-enhanced autonomous coding workflow.

Integrates superpowers methodologies into a LangGraph state machine:
  1. Task Classification    -- Router model classifies task type
  2. Memory Summarization   -- Past fixes recalled before spec writing
  3. Brainstorming          -- Spec refinement tailored to task type
  4. Writing Plans          -- Structured, acceptance-criteria-driven plans
  5. TDD on Disk            -- Tests run via pytest subprocess, real exit codes
  6. Systematic Debugging   -- Root-cause hypothesis, defense notes, one fix at a time
  7. Verification Gate      -- Automated checks override LLM opinion (hallucination guard)
  8. Procedural Memory      -- Successful debug fixes stored as reusable knowledge

Task types (classified by Router model):
  feature      -- New functionality (brainstorm + TDD + verify)
  audit        -- Deep review combining root-cause analysis, impact assessment, regression checks, and TDD.
  fix          -- Fix existing error (deep root-cause, no questions, TDD + verify)
  refactor     -- Restructure without changing behaviour (no questions, TDD + verify)
  edit         -- Intentional user-requested change WITH impact review
                  (heavier than fix: brainstorm lists affected callers before coding)
  create_skill -- Generate a new skill file in skills/ that gathers specific data
                  (API/scrape) and formats a report. Bypasses TDD loop.
  unclear      -- Insufficient info (ask 1-2 clarifying questions)

Model routing:
  Planner  (Qwen 3.5 9B)    -- brainstorm, plan, spec
  Router   (Nemotron 4B)    -- task classification
  Executor (Hermes 3 8B)    -- code generation, test writing, fixes, review

API compatibility:
  Imports: core.tracer.tracer singleton, core.llm.llm singleton
  Config:  cfg.planner_model, cfg.executor_model, cfg.router_model (no cfg.get())
  Git:     git(operation) -- init|snapshot|commit|rollback|log|status|diff only
  Tracer:  tracer.step(trace_id, node, message, **kwargs) API

Usage:
    from autocode import run_autocode_agent
    result = run_autocode_agent(
        task="Add input validation to memory store",
        files={"core/memory.py": open("core/memory.py").read()},
    )
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, TypedDict

# =============================================================================
# PLATFORM ENCODING FIX - Must be before subprocess calls
# =============================================================================
if sys.platform == 'win32':
    # Force UTF-8 mode on Windows for all subprocess operations
    os.environ['PYTHONUTF8'] = '1'

from langgraph.graph import END, StateGraph
from filelock import FileLock, Timeout

from core.config  import cfg
from core.tracer  import tracer
from core.llm     import llm

# =============================================================================
# IMPORTS FROM autocode_helpers
# =============================================================================

# Constants
from workflows.autocode_helpers.constants import (
    TASK_CLASSIFIER_SYSTEM,
    BRAINSTORM_SYSTEM,
    AUDIT_BRAINSTORM_SYSTEM,
    FIX_BRAINSTORM_SYSTEM,
    EDIT_BRAINSTORM_SYSTEM,
    REFACTOR_BRAINSTORM_SYSTEM,
    CREATE_SKILL_SYSTEM,
    PLAN_SYSTEM,
    TEST_SYSTEM,
    CODER_SYSTEM,
    DEBUG_SYSTEM,
    VERIFY_SYSTEM,
)

# State
from workflows.autocode_helpers.state import (
    AutocodeState,
    _default_state,
    MAX_RETRIES,
    MAX_FILE_CHARS,
    DEBUG,
    PLANNER_TIMEOUT,
    EXECUTOR_TIMEOUT,
    ROUTER_TIMEOUT,
    AGENT_ROOT,
)

# Helpers
from workflows.autocode_helpers.helpers import (
    _files_context,
    _extract_code,
    _parse_json,
    _parse_json_array,
    _should_copy_file,
    _call,
)

# Test runner
from workflows.autocode_helpers.test_runner import run_tests_on_disk

# Git ops
from workflows.autocode_helpers.git_ops import (
    _git_snapshot,
    _git_commit,
    _git_create_branch,
)

# Nodes
from workflows.autocode_helpers.nodes.classify import node_classify_task
from workflows.autocode_helpers.nodes.brainstorm import node_brainstorm
from workflows.autocode_helpers.nodes.plan import node_write_plan
from workflows.autocode_helpers.nodes.branch import node_git_branch
from workflows.autocode_helpers.nodes.tests import node_write_tests
from workflows.autocode_helpers.nodes.execute import node_execute_step
from workflows.autocode_helpers.nodes.run_tests import node_run_tests
from workflows.autocode_helpers.nodes.debug import node_systematic_debug
from workflows.autocode_helpers.nodes.write_files import (
    node_write_files,
    node_write_files_with_flag_reset,
)
from workflows.autocode_helpers.nodes.verify import node_verify
from workflows.autocode_helpers.nodes.commit import node_commit
from workflows.autocode_helpers.nodes.memory import node_distill_memory
from workflows.autocode_helpers.nodes.create_skill import node_create_skill

# Routes
from workflows.autocode_helpers.routes import (
    route_after_classify,
    route_after_brainstorm,
    route_after_run_tests,
    route_after_debug,
    route_after_write_files,
    route_after_verify,
)

# Graph
from workflows.autocode_helpers.graph import build_graph, get_graph

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_autocode_agent(
    task: str,
    files: dict[str, str] | None = None,
    mode: str = "feature",
    target_file: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Main entry point for the autocode workflow.

    Args:
        task: The task description
        files: Dictionary of file paths to content
        mode: The autocode mode (feature, fix_error, improve, add_feature, edit, create_skill, audit)
        target_file: The target file for the operation
        dry_run: If True, don't actually write files or commit

    Returns:
        Dict with status, result, trace_id, commit_sha, error, etc.
    """
    tid = tracer.new_trace("autocode", goal=task)

    state = _default_state(
        task=task,
        files=files or {},
        mode=mode,
        target_file=target_file,
    )
    state["trace_id"] = tid
    state["dry_run"] = dry_run

    try:
        graph = get_graph()
        app = graph.compile()
        final_state = app.invoke(state)

        result = {
            "status": final_state.get("status", "failed"),
            "result": final_state.get("result", ""),
            "trace_id": tid,
            "commit_sha": final_state.get("commit_sha", ""),
            "error": final_state.get("error_log", ""),
        }

        if "verification_notes" in final_state:
            result["verification_notes"] = final_state["verification_notes"]
        if "modified_files" in final_state:
            result["modified_files"] = final_state["modified_files"]
        if "skill_created" in final_state:
            result["skill_created"] = final_state["skill_created"]

        if result["status"] == "done":
            tracer.finish(tid, success=True, result=result.get("result", ""))
        else:
            tracer.finish(tid, success=False, result=result.get("error", ""))

        return result

    except Exception as e:
        tracer.error(tid, "autocode", f"Unexpected error: {e}", exc_info=True)
        tracer.finish(tid, success=False, result=str(e))
        return {"status": "failed", "error": str(e), "trace_id": tid}

# =============================================================================
# BACKWARD COMPATIBILITY EXPORTS
# =============================================================================

__all__ = [
    # Main entry point
    "run_autocode_agent",
    # State
    "AutocodeState",
    "_default_state",
    "MAX_RETRIES",
    "MAX_FILE_CHARS",
    "DEBUG",
    "PLANNER_TIMEOUT",
    "EXECUTOR_TIMEOUT",
    "ROUTER_TIMEOUT",
    "AGENT_ROOT",
    # Constants
    "TASK_CLASSIFIER_SYSTEM",
    "BRAINSTORM_SYSTEM",
    "AUDIT_BRAINSTORM_SYSTEM",
    "FIX_BRAINSTORM_SYSTEM",
    "EDIT_BRAINSTORM_SYSTEM",
    "REFACTOR_BRAINSTORM_SYSTEM",
    "CREATE_SKILL_SYSTEM",
    "PLAN_SYSTEM",
    "TEST_SYSTEM",
    "CODER_SYSTEM",
    "DEBUG_SYSTEM",
    "VERIFY_SYSTEM",
    # Helpers
    "_files_context",
    "_extract_code",
    "_parse_json",
    "_parse_json_array",
    "_should_copy_file",
    "_call",
    # Test runner
    "run_tests_on_disk",
    # Git ops
    "_git_snapshot",
    "_git_commit",
    "_git_create_branch",
    # Nodes
    "node_classify_task",
    "node_brainstorm",
    "node_write_plan",
    "node_git_branch",
    "node_write_tests",
    "node_execute_step",
    "node_run_tests",
    "node_systematic_debug",
    "node_write_files",
    "node_write_files_with_flag_reset",
    "node_verify",
    "node_commit",
    "node_distill_memory",
    "node_create_skill",
    # Routes
    "route_after_classify",
    "route_after_brainstorm",
    "route_after_run_tests",
    "route_after_debug",
    "route_after_write_files",
    "route_after_verify",
    # Graph
    "build_graph",
    "get_graph",
]