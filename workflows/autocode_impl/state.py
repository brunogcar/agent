"""State definitions and defaults for autocode workflow.

[v2.0] Introduced nested sub-states (PlanState, TDDState, etc.) to group
related fields. During the v2.x migration track (Track M1, batches 1-3),
nodes wrote to BOTH sub-state and legacy flat-field mirrors so that
unmigrated readers could keep reading the flat fields.

[v3.0] Flat-field removal — Track M1 is complete (all 8 accessors were
safe since v2.7). This module now:
  * Drops the legacy flat-field declarations from AutocodeState.
  * Drops the flat-field mirrors from _default_state().
  * Simplifies the 8 accessor functions to read sub-state ONLY (no
    legacy fallback).
  * Keeps the ephemeral flat fields (test_results, test_code,
    execution_notes, etc.) which are not part of any sub-state.

Nodes that previously returned flat-field mirrors alongside the
sub-state now return sub-state ONLY — callers must use accessors.

[v1.2] Removed unused `Optional` from typing import (no Optional[X]
annotations remain after the v3.0 cleanup).
"""

from __future__ import annotations

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing import Annotated, TypedDict, Any

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
# These are the PRIMARY storage since v3.0 (flat legacy mirrors removed).

class PlanState(TypedDict, total=False):
    """[v2.0] Planning sub-state — groups brainstorm/plan fields."""
    brainstorm_notes: str
    plan: list[dict]
    plan_accepted: bool
    spec: str
    current_step: int


class TDDState(TypedDict, total=False):
    """[v2.0] TDD loop sub-state — groups test/debug iteration fields.

    [v3.0] `test_results` removed from here — it's ephemeral and stays
    flat-only (written by run_pytest + run_tests, read directly by
    debug, verify, report, _shape_artifacts).
    """
    iteration: int
    source_code: str
    error: str
    status: str
    max_retries: int
    last_test_error: str  # [#39] stuck detection
    tests_written: bool
    debug_history: list[dict]  # [v2.0] Accumulated debug iterations for context summarization (#37)
    debug_summary: str  # [v2.0] Compressed debug_history from node_summarize_context


class FilesState(TypedDict, total=False):
    """[v2.0] Files sub-state — groups file tracking fields.

    [v3.0] `input_files` removed — the `files` core flat field is the input
    files dict (user-facing). Only `files_map` (snapshots) and `modified_files`
    (propagation) live in the sub-state.
    """
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
    """[v2.0] Version control sub-state — groups git + GitHub fields.

    [v1.4 P2] `branch_name` removed — was declared but never written by any
    node. The `branch` field (written by plan.py via RMW) is the only one
    used. commit.py has a `_get_vcs(state, 'branch_name', '')` fallback that
    now always returns "" — harmless, kept for backward compat with any
    caller that might have set branch_name directly in tests.
    """
    commit_sha: str
    branch: str
    pushed: bool
    pr_number: int
    pr_url: str


class MemoryState(TypedDict, total=False):
    """[v2.0] Memory sub-state."""
    notes: str
    # context removed — use the flat memory_context field instead (brainstorm.py writes it)


class AutocodeState(TypedDict, total=False):
    """State for the autocode workflow.

    [v3.0] Sub-state fields (plan_state, tdd, files_state, impact, debug,
    verify, vcs, memory) are the PRIMARY storage. Nodes read via accessor
    functions (_get_tdd, _get_plan, etc.) which read sub-state ONLY.

    The flat fields below are core/ephemeral fields that are NOT part of
    any sub-state: task/files/mode (core), task_type/project_root
    (classification), test_code/test_results/_pytest_output/tests_passed
    (ephemeral test), lint_output/lint_passed/llm_review_data (ephemeral
    verify), execution_notes (ephemeral), skill_path/skill_created
    (skill), status/error/result/messages (status),
    patch_errors/evidence_outputs/memory_context (ephemeral).

    [v1.4 P2] `target_file` and `error_log` removed — were declared but
    never written by any autocode node. `target_file` is still accepted as
    a _default_state() function param (workflow type handler enforces it)
    and stored in the state dict at runtime, but no autocode node reads it.
    `error_log` is read by node_distill_memory via .get() with default "",
    so removing the TypedDict declaration doesn't break that read.
    """

    # Core task (stays flat — used everywhere)
    task: str
    files: dict[str, str]
    mode: str
    trace_id: str
    dry_run: bool

    # Classification (stays flat — used everywhere)
    task_type: str
    project_root: str
    autocode_run_path: str

    # [v2.0] Sub-states (PRIMARY storage since v3.0)
    plan_state: PlanState
    tdd: TDDState
    files_state: FilesState
    impact: ImpactState
    debug: DebugState
    verify: VerifyState
    vcs: VCSState
    memory: MemoryState

    # Ephemeral test execution (stays flat — written by run_pytest + tests.py)
    test_code: list[str]  # Code blocks from _extract_code. Joined with \n\n in persist_artifacts.
    test_files: list[str]
    test_results: dict
    _pytest_output: str
    tests_passed: bool

    # Ephemeral verify (stays flat — written by run_lint + llm_review)
    lint_output: str
    lint_passed: bool | None
    llm_review_data: dict

    # Ephemeral execution (stays flat — written by execute + others)
    execution_notes: str  # written by node_execute_step
    # [v1.4 P2] error_log removed — never written by any node (was always "").

    # Skill (stays flat — set by create_skill path)
    skill_path: str
    skill_created: bool

    # Ephemeral output collections (stays flat)
    patch_errors: list[str]
    evidence_outputs: dict
    memory_context: str

    # Messages (with reducer)
    messages: Annotated[list[AnyMessage], add_messages]

    # Status (stays flat — read by routes + facade)
    status: str
    error: str
    result: str


# [v3.0] Accessor functions — read sub-state ONLY.
# The legacy flat-field fallback branches were removed in v3.0 once all 8
# sub-states had RMW writers and accessor readers (Track M1 complete).

def _get_plan(state: dict, key: str, default: Any = None) -> Any:
    """Read a plan sub-state field.

    [v2.0-rc3] The plan sub-state lives under "plan_state" (not "plan")
    because "plan" is overloaded — legacy code reads it as list[dict].
    """
    sub = state.get("plan_state")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_tdd(state: dict, key: str, default: Any = None) -> Any:
    """Read a TDD sub-state field."""
    sub = state.get("tdd")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_files(state: dict, key: str, default: Any = None) -> Any:
    """Read a files sub-state field."""
    sub = state.get("files_state")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_impact(state: dict, key: str, default: Any = None) -> Any:
    """Read an impact sub-state field."""
    sub = state.get("impact")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_debug(state: dict, key: str, default: Any = None) -> Any:
    """Read a debug sub-state field."""
    sub = state.get("debug")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_verify(state: dict, key: str, default: Any = None) -> Any:
    """Read a verify sub-state field."""
    sub = state.get("verify")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_vcs(state: dict, key: str, default: Any = None) -> Any:
    """Read a VCS sub-state field."""
    sub = state.get("vcs")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _get_memory(state: dict, key: str, default: Any = None) -> Any:
    """Read a memory sub-state field."""
    sub = state.get("memory")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default


def _default_state(
    task: str = "",
    files: dict[str, str] = None,
    mode: str = "",
    target_file: str = "",
    dry_run: bool = False,
) -> dict:
    """Create a default state dictionary.

    [v3.0] Sub-states are the PRIMARY (and only) storage for the grouped
    fields — the legacy flat-field mirrors that _default_state used to
    write alongside the sub-states have been removed. The remaining flat
    fields are core/ephemeral (task, files, mode, test_code, test_results,
    execution_notes, status, etc.) which are not part of any sub-state.

    Accessors (_get_tdd, _get_vcs, etc.) read sub-state ONLY — there is
    no legacy fallback. Tests + nodes must use accessors for sub-state
    fields.
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
        # [v2.0-rc3] Sub-states are PRIMARY storage (populated with defaults)
        "plan_state": {
            "brainstorm_notes": "",
            "plan": [],
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
            "tests_written": False,
            "debug_history": [],
            "debug_summary": "",
        },
        "files_state": {
            "files_map": {},  # [v3.0] input_files removed — files is core flat field
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
        # Ephemeral flat fields (not part of any sub-state)
        "test_code": "",
        "test_files": [],
        "test_results": {},
        "_pytest_output": "",
        "tests_passed": False,
        "lint_output": "",
        "lint_passed": None,
        "llm_review_data": {},
        "execution_notes": "",
        "error_log": "",
        "skill_path": "",
        "skill_created": False,
        "patch_errors": [],
        "evidence_outputs": {},
        "memory_context": "",
        "messages": [],
        "status": "running",
        "error": "",
        "result": "",
    }
