"""
State management for autocode workflow.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, TypedDict

from core.config import cfg

# ── Tunables ------------------------------------------------------------------

MAX_RETRIES:    int  = cfg.autocode_max_retries
MAX_FILE_CHARS: int  = cfg.autocode_max_file_chars
DEBUG:          bool = getattr(cfg, "autocode_debug", False)

PLANNER_TIMEOUT:  int = 90
EXECUTOR_TIMEOUT: int = 120
ROUTER_TIMEOUT:   int = 15

# autocode writes to the AGENT root (not workspace) when editing agent code.
# Skills and workspace projects use cfg.workspace_root.
AGENT_ROOT: Path = cfg.agent_root

# ── State TypedDict -----------------------------------------------------------

class AutocodeState(TypedDict, total=False):
    # Inputs
    task:           str
    files:          dict[str, str]
    mode:           str          # "feature" | "fix_error" | "improve" | "add_feature"
                                 # "edit" | "create_skill" | "audit"
    target_file:    str

    # Classification
    task_type:      str          # "feature" | "fix" | "refactor" | "edit"
                                 # "create_skill" | "audit" | "unclear"
    memory_context: str

    # Planning
    spec:           str
    plan:           list[dict]
    branch:         str
    current_step:   int
    step_attempt:   int

    # Execution
    generated_code: str
    test_code:      str
    test_result:    str
    error_log:      str

    # Debugging
    hypothesis:     str
    defense_note:   str
    debug_attempts: int
    came_from_debug: bool

    # Verification
    verification_passed: bool
    verification_notes:  str
    evidence_outputs:    dict    # {"tests": "...", "lint": "...", "regression": "..."}

    # Result
    status:     str              # "running" | "done" | "failed" | "needs_clarification"
    result:     str
    commit_sha: str
    trace_id:   str
    skill_path: str              # set by node_create_skill, e.g. "skills/news_headlines.py"

def _default_state(task: str, files: dict[str, str], mode: str = "feature",
                   target_file: str = "") -> AutocodeState:
    return AutocodeState(
        task=task,
        files={k: v[:MAX_FILE_CHARS] for k, v in files.items()},
        mode=mode,
        target_file=target_file,
        task_type="feature",
        memory_context="",
        spec="",
        plan=[],
        branch="",
        current_step=0,
        step_attempt=0,
        generated_code="",
        test_code="",
        test_result="",
        error_log="",
        hypothesis="",
        defense_note="",
        debug_attempts=0,
        came_from_debug=False,
        verification_passed=False,
        verification_notes="",
        evidence_outputs={},
        status="running",
        result="",
        commit_sha="",
        trace_id="",
        skill_path="",
    )