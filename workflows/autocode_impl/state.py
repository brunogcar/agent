"""State definitions and defaults for autocode workflow."""

from __future__ import annotations

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing import Annotated, TypedDict, Optional

from core.config import cfg

# [Bug #9] Removed dead AGENT_ROOT = None — was never set or used.
# Autocode operates on workspace projects via target_file, and uses
# cfg.agent_root / cfg.workspace_root directly when path resolution is needed.

# Constants (Centralized in core.config.cfg, referenced here for local defaults)
MAX_RETRIES = cfg.autocode_max_retries
MAX_FILE_CHARS = cfg.autocode_max_file_chars
DEBUG = cfg.autocode_debug
PLANNER_TIMEOUT = cfg.planner_timeout
EXECUTOR_TIMEOUT = cfg.execution_timeout
ROUTER_TIMEOUT = cfg.router_timeout

# Timeout configuration centralized in core.config.cfg.model_registry
# Each role has its own timeout: cfg.model_registry[role]["timeout"]
# No local NODE_TIMEOUTS needed

class FileSnapshot(TypedDict):
    """Memory-safe snapshot for LangGraph state to prevent bloat."""
    content_preview: str
    preview_md5: str
    full_md5: str
    size: int
    truncated: bool

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
    project_root: str
    autocode_run_path: str

    # Brainstorm/Plan
    brainstorm_notes: str
    plan: list[dict]
    plan_accepted: bool
    spec: str

    # TDD loop
    tdd_iteration: int
    tdd_source_code: str
    tdd_error: str
    tdd_status: str
    max_retries: int
    files_map: dict[str, FileSnapshot]
    current_step: int
    last_test_error: str  # [#39] stuck detection: previous iteration's error signature

    # Execution
    execution_notes: str
    modified_files: list[str]

    # Test results
    test_results: dict
    tests_written: bool

    # Impact Analysis (Phase: AST Dependency Graphing)
    # [Bug #8] Changed from list[str] to list[dict] — analyze_impact returns
    # structured warnings: {"type": str, "message": str, "agent_fault": bool}
    impact_warnings: list[dict]
    targeted_test_cmd: str | None
    analyze_impact_failed: bool

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
    branch: str  # [v1.3] Fix TypedDict drift — was read by branch.py but not declared

    # [v1.3] GitHub + Swarm integration
    pushed: bool
    pr_number: int
    pr_url: str
    swarm_verdict: dict  # {confidence: HIGH|MEDIUM|LOW, agreement: str, providers: int}

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
    dry_run: bool = False,
) -> dict:
    """Create a default state dictionary."""
    return {
        "task": task,
        "files": files or {},
        "mode": mode,
        "target_file": target_file,
        "trace_id": "",
        "dry_run": dry_run,
        "task_type": "",
        "project_root": "",
        "autocode_run_path": "",
        "brainstorm_notes": "",
        "plan": [],
        "plan_accepted": False,
        "spec": "",
        "tdd_iteration": 0,
        "tdd_source_code": "",
        "tdd_error": "",
        "tdd_status": "",
        "max_retries": MAX_RETRIES,
        "files_map": {},
        "current_step": 0,
        "last_test_error": "",  # [#39] stuck detection
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
        "branch": "",  # [v1.3] Fix TypedDict drift
        # [v1.3] GitHub + Swarm integration defaults
        "pushed": False,
        "pr_number": 0,
        "pr_url": "",
        "swarm_verdict": {},
        "memory_notes": "",
        "messages": [],
        "status": "running",
        "error": "",
        "result": "",
    }
