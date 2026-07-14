"""State definitions and defaults for autocode workflow.

[v2.0] Introduces nested sub-states (PlanState, TDDState, etc.) to group
related fields. The flat legacy fields are kept for backward compatibility
during the migration (Phase 2-5). Phase 6 removes the legacy fields.

Nodes should use the accessor functions (_get_tdd, _get_plan, etc.) which
read from the nested sub-state if present, falling back to the legacy flat
field. This allows incremental migration without breaking any node.
"""

from __future__ import annotations

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing import Annotated, TypedDict, Optional, Any

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


# [v2.0] Sub-state TypedDicts — group related fields for clarity.
# These are optional in Phase 2 (nodes use accessors with legacy fallback).
# Phase 6 makes them the primary storage and removes the legacy flat fields.

class PlanState(TypedDict, total=False):
    """[v2.0] Planning sub-state — groups brainstorm/plan fields."""
    brainstorm_notes: str
    plan: list[dict]
    plan_accepted: bool
    spec: str
    current_step: int


class TDDState(TypedDict, total=False):
    """[v2.0] TDD loop sub-state — groups test/debug iteration fields."""
    iteration: int
    source_code: str
    error: str
    status: str
    max_retries: int
    last_test_error: str  # [#39] stuck detection
    test_results: dict
    tests_written: bool
    debug_history: list[dict]  # [v2.0] Accumulated debug iterations for context summarization (#37)
    debug_summary: str  # [v2.0] Compressed debug_history from node_summarize_context


class FilesState(TypedDict, total=False):
    """[v2.0] Files sub-state — groups file tracking fields."""
    input_files: dict[str, str]
    files_map: dict[str, FileSnapshot]
    modified_files: list[str]


class ImpactState(TypedDict, total=False):
    """[v2.0] Impact analysis sub-state."""
    warnings: list[dict]
    targeted_test_cmd: str | None
    failed: bool


class DebugState(TypedDict, total=False):
    """[v2.0] Debug sub-state — groups debug analysis fields."""
    notes: str
    root_cause: str
    defense_notes: str
    swarm_verdict: dict
    subagent_verdict: dict  # [v2.0.4] P1-1: subagent debug path verdict (was doc'd but never set)


class VerifyState(TypedDict, total=False):
    """[v2.0] Verification sub-state."""
    notes: str
    report: str
    passed: bool


class VCSState(TypedDict, total=False):
    """[v2.0] Version control sub-state — groups git + GitHub fields."""
    commit_sha: str
    branch: str
    branch_name: str
    pushed: bool
    pr_number: int
    pr_url: str


class MemoryState(TypedDict, total=False):
    """[v2.0] Memory sub-state."""
    notes: str
    context: str


class AutocodeState(TypedDict, total=False):
    """State for the autocode workflow.

    [v2.0] Sub-state fields (plan, tdd, files, etc.) are optional during
    migration. Nodes use accessor functions that read sub-state first,
    fall back to legacy flat fields.
    """

    # Core task (stays flat — used everywhere)
    task: str
    files: dict[str, str]
    mode: str
    target_file: str
    trace_id: str
    dry_run: bool

    # Classification (stays flat — used everywhere)
    task_type: str
    project_root: str
    autocode_run_path: str

    # [v2.0] Sub-states (optional — Phase 2-5 migration)
    plan: PlanState
    plan_state: PlanState  # [v2.0.5] P2-2: sub-state primary storage (not "plan" — that's overloaded as list[dict])
    tdd: TDDState
    files_state: FilesState
    impact: ImpactState
    debug: DebugState
    verify: VerifyState
    vcs: VCSState
    memory: MemoryState

    # --- Legacy flat fields (kept for backward compat during migration) ---
    # Note: `plan` is declared above as PlanState (sub-state). In legacy code,
    # `plan` holds a list[dict] (the step list). The _get_plan() accessor
    # handles both by checking isinstance. This overload is intentional during
    # migration — Phase 6 will resolve it when legacy fields are removed.
    brainstorm_notes: str
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
    verification_passed: bool  # [v2.0.5] P2-1: was undeclared (route_after_verify + commit.py read it)

    # Git
    commit_sha: str
    branch_name: str
    branch: str  # [v1.3] Fix TypedDict drift — was read by branch.py but not declared

    # [v1.3] GitHub + Swarm integration
    pushed: bool
    pr_number: int
    pr_url: str
    swarm_verdict: dict  # {confidence: HIGH|MEDIUM|LOW, agreement: str, providers: int}
    subagent_verdict: dict  # [v2.0.4] P1-1: {fix, root_cause, defense_notes} from subagent debug path

    # Memory
    memory_notes: str

    # Messages (with reducer)
    messages: Annotated[list[AnyMessage], add_messages]

    # Status
    status: str
    error: str
    result: str


# [v2.0] Backward-compat accessor functions.
# These read from the nested sub-state if present, falling back to the
# legacy flat field. Nodes migrate to use these incrementally.
# Phase 6 removes the legacy fallbacks + flat fields.

def _get_plan(state: dict, key: str, default: Any = None) -> Any:
    """Read a plan sub-state field, falling back to legacy flat field.

    [v2.0-rc3] Phase 6: plan sub-state lives under "plan_state" (not "plan")
    because "plan" is overloaded — legacy code reads it as list[dict].
    """
    plan_state = state.get("plan_state")
    if isinstance(plan_state, dict) and key in plan_state:
        return plan_state[key]
    # Legacy flat field
    return state.get(key, default)


def _get_tdd(state: dict, key: str, default: Any = None) -> Any:
    """Read a TDD sub-state field, falling back to legacy flat field.

    Maps short keys to legacy prefixed keys:
        iteration -> tdd_iteration
        source_code -> tdd_source_code
        error -> tdd_error
        status -> tdd_status
    """
    tdd = state.get("tdd")
    if isinstance(tdd, dict) and key in tdd:
        return tdd[key]
    # Legacy flat field — map short key to prefixed key
    legacy_key = f"tdd_{key}" if key in ("iteration", "source_code", "error", "status") else key
    return state.get(legacy_key, default)


def _get_files(state: dict, key: str, default: Any = None) -> Any:
    """Read a files sub-state field, falling back to legacy flat field."""
    files_state = state.get("files_state")
    if isinstance(files_state, dict) and key in files_state:
        return files_state[key]
    # input_files -> files (legacy), files_map -> files_map, modified_files -> modified_files
    if key == "input_files":
        return state.get("files", default)
    return state.get(key, default)


def _get_impact(state: dict, key: str, default: Any = None) -> Any:
    """Read an impact sub-state field, falling back to legacy flat field.

    Maps short keys to legacy prefixed keys:
        warnings -> impact_warnings
        failed -> analyze_impact_failed
    """
    impact = state.get("impact")
    if isinstance(impact, dict) and key in impact:
        return impact[key]
    legacy_map = {"warnings": "impact_warnings", "failed": "analyze_impact_failed"}
    legacy_key = legacy_map.get(key, key)
    return state.get(legacy_key, default)


def _get_debug(state: dict, key: str, default: Any = None) -> Any:
    """Read a debug sub-state field, falling back to legacy flat field.

    [v2.5] Maps short keys to legacy keys:
        notes -> debug_notes
    Other keys (root_cause, defense_notes, swarm_verdict, subagent_verdict)
    are the same in both sub-state and flat field.
    """
    debug = state.get("debug")
    if isinstance(debug, dict) and key in debug:
        return debug[key]
    legacy_map = {"notes": "debug_notes"}
    legacy_key = legacy_map.get(key, key)
    return state.get(legacy_key, default)


def _get_verify(state: dict, key: str, default: Any = None) -> Any:
    """Read a verify sub-state field, falling back to legacy flat field.

    Maps short keys to legacy keys:
        notes -> verification_notes
        report -> verify_report
        passed -> verification_passed
    """
    verify = state.get("verify")
    if isinstance(verify, dict) and key in verify:
        return verify[key]
    legacy_map = {"notes": "verification_notes", "report": "verify_report", "passed": "verification_passed"}
    legacy_key = legacy_map.get(key, key)
    return state.get(legacy_key, default)


def _get_vcs(state: dict, key: str, default: Any = None) -> Any:
    """Read a VCS sub-state field, falling back to legacy flat field."""
    vcs = state.get("vcs")
    if isinstance(vcs, dict) and key in vcs:
        return vcs[key]
    return state.get(key, default)


def _get_memory(state: dict, key: str, default: Any = None) -> Any:
    """Read a memory sub-state field, falling back to legacy flat field."""
    memory = state.get("memory")
    if isinstance(memory, dict) and key in memory:
        return memory[key]
    # notes -> memory_notes (legacy)
    if key == "notes":
        return state.get("memory_notes", default)
    return state.get(key, default)


def _default_state(
    task: str = "",
    files: dict[str, str] = None,
    mode: str = "",
    target_file: str = "",
    dry_run: bool = False,
) -> dict:
    """Create a default state dictionary.

    [v2.0-rc3] Phase 6: sub-states are now PRIMARY storage (populated with
    default values). Legacy flat fields are kept as mirrors for backward
    compat with unmigrated nodes + tests. Phase 7 will remove the legacy
    fields after all nodes + tests are migrated to accessors.

    Accessors (_get_tdd, _get_vcs, etc.) read sub-state first, fall back to
    legacy. Since sub-states are now populated, accessors always find values
    in sub-states — the legacy fallback is only hit by code that reads
    state.get("tdd_iteration") directly (bypassing accessors).
    """
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
        # [v2.0-rc3] Phase 6: sub-states are PRIMARY storage (populated with defaults)
        # Note: "plan" key is overloaded — legacy code reads it as list[dict] (step list).
        # The plan sub-state lives under "plan_state" to avoid breaking list readers.
        "plan_state": {
            "brainstorm_notes": "",
            "steps": [],  # the actual plan step list (was "plan" in legacy)
            "plan_accepted": False,
            "spec": "",
            "current_step": 0,
        },
        "tdd": {
            "iteration": 0,
            "source_code": "",
            "error": "",
            "status": "",
            "max_retries": MAX_RETRIES,
            "last_test_error": "",
            "test_results": {},
            "tests_written": False,
            "debug_history": [],
            "debug_summary": "",
        },
        "files_state": {
            "input_files": files or {},
            "files_map": {},
            "modified_files": [],
        },
        "impact": {
            "warnings": [],
            "targeted_test_cmd": None,
            "failed": False,
        },
        "debug": {
            "notes": "",
            "root_cause": "",
            "defense_notes": "",
            "swarm_verdict": {},
            "subagent_verdict": {},  # [v2.0.4] P1-1
        },
        "verify": {
            "notes": "",
            "report": "",
            "passed": False,
        },
        "vcs": {
            "commit_sha": "",
            "branch": "",
            "branch_name": "",
            "pushed": False,
            "pr_number": 0,
            "pr_url": "",
        },
        "memory": {
            "notes": "",
        },
        # Legacy flat fields (mirrors — kept for backward compat during Phase 6-7)
        "plan": [],  # legacy: list[dict] step list (plan_state["steps"] is the sub-state version)
        "brainstorm_notes": "",
        "plan_accepted": False,
        "spec": "",
        "tdd_iteration": 0,
        "tdd_source_code": "",
        "tdd_error": "",
        "tdd_status": "",
        "max_retries": MAX_RETRIES,
        "files_map": {},
        "current_step": 0,
        "last_test_error": "",
        "execution_notes": "",
        "modified_files": [],
        "test_results": {},
        "tests_written": False,
        "debug_notes": "",
        "root_cause": "",
        "defense_notes": "",
        "verification_notes": "",
        "verify_report": "",
        "verification_passed": False,  # [v2.0.5] P2-1: was missing from _default_state
        "commit_sha": "",
        "branch_name": "",
        "branch": "",
        "pushed": False,
        "pr_number": 0,
        "pr_url": "",
        "swarm_verdict": {},
        "subagent_verdict": {},  # [v2.0.4] P1-1
        "memory_notes": "",
        "messages": [],
        "status": "running",
        "error": "",
        "result": "",
    }
