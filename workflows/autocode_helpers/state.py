"""
State definitions and defaults for autocode workflow.
"""
from __future__ import annotations

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing import Annotated, TypedDict, Optional

from core.config import cfg  # [FIX 4] Added to read timeout config from env

# Constants
MAX_RETRIES = 3
MAX_FILE_CHARS = 50_000
DEBUG = False
PLANNER_TIMEOUT = 180
EXECUTOR_TIMEOUT = 120
ROUTER_TIMEOUT = 60
AGENT_ROOT = None  # Set via cfg

# [FIX 4] Timeout configuration aligned with config.py env vars
NODE_TIMEOUTS = {
    "planner": cfg.planner_timeout,
    "executor": cfg.execution_timeout,
    "verifier": getattr(cfg, "verifier_timeout", cfg.execution_timeout),
    "default": cfg.execution_timeout
}

class AutocodeState(TypedDict, total=False):
    """State for the autocode workflow."""

    # Core task
    task: str
    files: dict[str, str]
    mode: str
    target_file: str
    trace_id: str
    dry_run: bool

    # Classification
    task_type: str

    # Brainstorm/Plan
    brainstorm_notes: str
    plan: dict
    plan_accepted: bool

    # TDD loop
    tdd_iteration: int
    tdd_source_code: str
    tdd_error: str
    tdd_status: str
    max_retries: int
    files_map: dict

    # Execution
    execution_notes: str
    modified_files: list[str]

    # Test results
    test_results: dict
    tests_written: bool

    # Debug
    debug_notes: str
    root_cause: str
    defense_notes: str

    # Verification
    verification_notes: str
    verify_report: str

    # Git
    commit_sha: str
    branch_name: str

    # Memory
    memory_notes: str

    # Messages (with reducer)
    messages: Annotated[list[AnyMessage], add_messages]

    # Status
    status: str
    error: str
    result: str

def _default_state(
    task: str = "",
    files: dict[str, str] = None,
    mode: str = "",
    target_file: str = "",
) -> dict:
    """Create a default state dictionary."""
    return {
        "task": task,
        "files": files or {},
        "mode": mode,
        "target_file": target_file,
        "trace_id": "",
        "dry_run": False,
        "task_type": "",
        "brainstorm_notes": "",
        "plan": {},
        "plan_accepted": False,
        "spec": "",
        "tdd_iteration": 0,
        "tdd_source_code": "",
        "tdd_error": "",
        "tdd_status": "",
        "max_retries": MAX_RETRIES,
        "files_map": {},
        "execution_notes": "",
        "modified_files": [],
        "test_results": {},
        "tests_written": False,
        "debug_notes": "",
        "root_cause": "",
        "defense_notes": "",
        "verification_notes": "",
        "verify_report": "",
        "commit_sha": "",
        "branch_name": "",
        "memory_notes": "",
        "messages": [],
        "status": "running",
        "error": "",
        "result": "",
    }

# [FIX 1] REMOVED: _state_reducer function
# LangGraph's `add_messages` annotation handles accumulation automatically.
# The custom reducer conflicted with it, causing message replacement instead of append.