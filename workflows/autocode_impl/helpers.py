"""Helpers for autocode workflow."""
from __future__ import annotations
import re
import time as _time
import threading as _threading
from pathlib import Path
from core.config import cfg
from core.llm import llm
from core.tracer import tracer
from core.backoff_retry import retry_with_backoff

def _extract_code(text: str) -> list[str]:
    """Extract code blocks from text."""
    pattern = r"```(?:[^\n]*\n)?(.*?)```"
    matches = re.finditer(pattern, text, re.DOTALL)
    return [m.group(1).strip() for m in matches]

def _parse_json(text: str | None) -> dict:
    """Parse JSON from text, extracting from code blocks if needed.

    [v2.0] Now delegates to core.json_extract.extract_json — single source of
    truth for all LLM JSON parsing in the codebase.
    """
    from core.json_extract import extract_json
    return extract_json(text)

def _parse_json_array(text: str | None) -> list:
    """Parse JSON array from text.

    [v2.0] Now delegates to core.json_extract.extract_json_array.
    """
    from core.json_extract import extract_json_array
    return extract_json_array(text)

def _files_context(files: dict[str, str], max_len: int = 2000) -> str:
    """Format files dictionary for LLM context."""
    if not files:
        return "No files provided."
    context = []
    for path, content in files.items():
        context.append(f"# {path}\n{content[:max_len]}")
    return "\n\n".join(context)

def _should_copy_file(path: str | Path, protected_files: frozenset[str]) -> bool:
    """Check if a file should be copied (not protected)."""
    path_str = str(path).replace("\\", "/")
    name = Path(path).name
    return name not in protected_files and path_str not in protected_files


# [v2.0] Cancellation flag for graph-level timeout.
# When invoke_with_timeout() detects a timeout, it sets this flag.
# _call() checks it between retries — prevents waiting through a retry
# backoff when the graph has already timed out.
# [Hardening P1.7] _cancel_event lets request_cancellation() interrupt the
# time.sleep inside _call's retry backoff — was a non-interruptible 1-4s block.
_cancellation_requested = False
_cancel_event = _threading.Event()


def request_cancellation() -> None:
    """[v2.0] Set the cancellation flag — called by invoke_with_timeout on timeout.

    After this is called, _call() will raise RuntimeError on the next retry
    check instead of sleeping through the backoff.

    [Hardening P1.7] Also sets the Event so any in-progress backoff sleep in
    _call() wakes up immediately.
    """
    global _cancellation_requested
    _cancellation_requested = True
    _cancel_event.set()  # wake up any sleeping _call


def clear_cancellation() -> None:
    """[v2.0] Clear the cancellation flag — called at the start of a new graph invocation.

    [Hardening P1.7] Also clears the Event so subsequent _call() backoffs can sleep.
    """
    global _cancellation_requested
    _cancellation_requested = False
    _cancel_event.clear()


def is_cancellation_requested() -> bool:
    """[v2.0] Check if cancellation was requested."""
    return _cancellation_requested


# [v3.6 #35] Track the graph start time for deadline computation.
# Set by set_graph_start_time() (called from invoke_with_timeout at the
# start of each workflow run) and read by _remaining_timeout() to cap
# subprocess timeouts so they don't exceed the graph's remaining budget.
_graph_local = _threading.local()  # [v3.9 Bug A] per-thread start time (was module global)


def set_graph_start_time(timeout: int | None = None) -> None:
    """Record the graph invocation start time (+ optional resolved timeout) for
    deadline computation.

    Called by invoke_with_timeout() at the start of each workflow run.
    Used by _remaining_timeout() to cap subprocess timeouts so they
    don't exceed the graph's remaining time budget.

    [v3.6 #35] Incremental zombie fix — when the graph timeout fires
    (e.g., 300s), daemon threads blocked on subprocess.run() can linger
    for up to cfg.sandbox_timeout (e.g., 30s) past the deadline. Capping
    the subprocess timeout at the remaining graph budget bounds that
    linger to <=1s.

    [v3.11 B1] Accepts an optional `timeout` param — the RESOLVED per-run
    timeout (adaptive or static). When provided, _remaining_timeout() reads
    it instead of cfg.autocode_graph_timeout. Pre-v3.11, _remaining_timeout()
    always read the static cfg value, so adaptive timeouts (feature=900s,
    fix/refactor/edit=600s) were never communicated — a feature task at 400s
    elapsed (within its real 900s budget) computed remaining = 300 - 400 =
    -100 → 1, giving pytest a spurious 1-second timeout.
    """
    _graph_local.start_time = _time.time()  # [v3.9 Bug A] per-thread (was module global)
    # [v3.11 B1] Store the resolved per-run timeout so _remaining_timeout()
    # can use it instead of the static cfg.autocode_graph_timeout. None =
    # fall back to cfg (backward-compatible with v3.10 callers that don't
    # pass timeout).
    _graph_local.timeout = timeout


def _remaining_timeout(default_timeout: int) -> int:
    """Compute remaining time budget for a subprocess call.

    Returns min(default_timeout, remaining_graph_time).
    If the graph start time wasn't set (e.g., unit tests), returns default_timeout.
    If the remaining time is <= 0, returns 1 (minimum — let the subprocess
    try, then the post-check will catch the cancellation).

    [v3.6 #35] Used by run_pytest/run_lint/run_tests nodes to cap their
    subprocess.run(timeout=...) so the subprocess can't outlive the graph
    deadline by more than 1s.

    [v3.11 B1] Reads the resolved per-run timeout (stored by
    set_graph_start_time(timeout=...)) instead of cfg.autocode_graph_timeout.
    Pre-v3.11, a feature task with adaptive timeout=900s would still use the
    static cfg.autocode_graph_timeout=300s here — at 400s elapsed, remaining =
    300-400 = -100 → 1, giving pytest a spurious 1-second timeout. Now reads
    the actual 900s budget → remaining = 900-400 = 500. Falls back to cfg when
    the per-run timeout wasn't set (legacy callers / unit tests).
    """
    from core.config import cfg
    start = getattr(_graph_local, 'start_time', 0.0)
    if start == 0.0:
        return default_timeout
    # [v3.11 B1] Use the per-run timeout (set by invoke_with_timeout) when
    # available; fall back to the static cfg default for backward compat.
    graph_timeout = getattr(_graph_local, 'timeout', None)
    if graph_timeout is None:
        graph_timeout = cfg.autocode_graph_timeout
    elapsed = _time.time() - start
    remaining = graph_timeout - elapsed
    if remaining <= 0:
        return 1  # expired — minimal timeout, post-check will bail
    return int(min(default_timeout, remaining))


def _cancelled() -> bool:
    """Check if cancellation was requested. Shortcut for is_cancellation_requested()."""
    return _cancellation_requested


def _call(role: str, system: str, user: str, timeout: int | None = None, temperature: float | None = None, json_schema: dict | None = None, retries: int = 2, trace_id: str = "") -> str:
    """Call the LLM with the given role, system prompt, and user message.

    v1.3: Added json_schema param for structured generation. When provided,
    LM Studio enforces the schema at generation time via outlines.
    [Pre-2.0 Fix] Added retry with exponential backoff for transient failures.
    Was: single attempt — a rate limit or network blip crashed the entire workflow.
    [v2.0] Added cancellation flag check between retries — prevents waiting
    through a retry backoff when the graph has already timed out.
    [Hardening P1.7] Backoff sleep is now interruptible via _cancel_event.wait
    so request_cancellation() can wake the thread immediately.
    [v2.0.5] P3-1: Added trace_id param so retry-exhaustion errors are traced to
    the workflow's trace (was: empty trace_id — errors were unattributed).
    [v1.10 / Phase C] Retry loop now delegates to core.backoff_retry.retry_with_backoff.
    Cancellation integration is via the `cancellation_check` callable (the
    autocode module-global `is_cancellation_requested`). The fn closure wraps
    the llm.complete call + response.ok check (raising on non-ok). Returns
    the response text on success.
    """
    if timeout is None:
        timeout = cfg.model_registry.get(role, {}).get("timeout", cfg.execution_timeout)

    def _attempt() -> str:
        """Single LLM attempt. Raises on any failure (triggers a retry)."""
        # [v2.0] Check cancellation flag before each attempt — if the graph
        # timed out during a previous retry's backoff sleep, bail immediately.
        # (retry_with_backoff also checks cancellation_check before each
        # attempt, but this explicit check preserves the original error
        # message for backward compat with tests that assert on it.)
        if _cancellation_requested:
            raise RuntimeError("LLM call cancelled — graph timeout exceeded")
        response = llm.complete(
            role=role,
            system=system,
            user=user,
            timeout=timeout,
            temperature=temperature,
            json_schema=json_schema,
        )
        if response.ok:
            return response.text
        raise RuntimeError(f"LLM error: {response.error}")

    # [v1.10 / Phase C] Use the shared retry helper. cancellation_check is
    # the autocode module-global flag (kept as-is — too risky to migrate to
    # workflows.base.is_workflow_cancelled in this refactor). The helper
    # checks it BEFORE each attempt AND polls it during interruptible backoff.
    return retry_with_backoff(
        _attempt,
        retries=retries,
        base_delay=2.0,
        cancellation_check=is_cancellation_requested,
        tid=trace_id,
    )

# [v2.0] Phase 7: _write_files() DELETED — was dead code (never called by any node).
# The actual file writing logic lives in nodes/apply_patches.py + nodes/write_new_files.py.

def _get_autocode_run_path(trace_id: str) -> Path:
    """Return per-run autocode directory: workspace/autocode/YYYYMMDD/{trace_id}/"""
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    run_dir = cfg.workspace_root / "autocode" / date_str / trace_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def _cleanup_old_autocode_runs(max_age_days: int = 7) -> None:
    """Delete autocode run folders older than max_age_days. Called on-demand."""
    import shutil
    from datetime import datetime, timedelta
    autocode_base = cfg.workspace_root / "autocode"
    if not autocode_base.exists():
        return
    # [v1.1 FIX] Create ONE trace for the entire cleanup sweep, not one per
    # directory. Previously called tracer.step("autocode", ...) with a literal
    # string trace_id, causing trace collisions. See:
    # docs/core/observability/CHANGELOG.md (v1.1)
    _tid = tracer.new_trace("autocode_cleanup", goal="artifact cleanup")
    cutoff = datetime.now() - timedelta(days=max_age_days)
    for date_dir in autocode_base.iterdir():
        if not date_dir.is_dir() or not date_dir.name.isdigit() or len(date_dir.name) != 8:
            continue
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y%m%d")
            if dir_date < cutoff:
                shutil.rmtree(date_dir, ignore_errors=True)
                tracer.step(_tid, "cleanup", f"Removed old autocode dir: {date_dir}")
        except (ValueError, OSError):
            continue


def _blast_radius_warning(project_root: str, files: list[str], tid: str) -> str:
    """[v1.4 P2] Return BLAST RADIUS WARNING string, or '' if no callers found.

    Extracted from near-identical inline blocks in plan.py (Phase 8) and
    debug.py (Phase 6). Both blocks did the same thing — query kgraph for
    callers of the files being modified, warn if any callers exist outside
    the modified set.
    """
    if not project_root or not files:
        return ""
    try:
        from core.kgraph.queries import get_callers
        from core.kgraph.project import ProjectManager
        is_agent = str(Path(project_root).resolve()) == str(cfg.agent_root.resolve())
        pm = ProjectManager(project_root, is_agent_root=is_agent)
        callers = []
        for f in files[:3]:
            deps = get_callers(pm.path, f)
            callers.extend([c for c in deps if c not in files])
        if not callers:
            return ""
        unique = sorted(set(callers))[:5]  # [v3.9 Bug F] deterministic order
        return f"\n\n⚠️ BLAST RADIUS WARNING: The files you are modifying are also used by: {', '.join(unique)}. Ensure your fix does not break these callers."
    except Exception as e:
        tracer.warning(tid, "blast_radius", f"Query failed: {e}")
        return ""


# [v3.3 #58] Canonical skip-status set for all nodes.
# Nodes should use _should_skip_node(state) instead of inline status checks.
# The set includes all terminal/error statuses that mean "don't run this node".
_SKIP_STATUSES = frozenset({
    "needs_clarification",  # node_brainstorm asked questions → wait for user input
    "failed",               # a previous node failed → skip downstream
    "error",                # a previous node errored → skip downstream
    "skipped",              # a previous node was skipped (e.g. dry_run) → skip downstream
})


def _should_skip_node(state: dict) -> bool:
    """Check if the current node should be skipped based on the workflow status.

    [v3.3 #58] Standardizes the status-check pattern across all nodes.
    Before this, nodes had 4 different sets:
      - ("needs_clarification", "failed") — missing "error" + "skipped"
      - ("needs_clarification", "failed", "error") — missing "skipped"
      - ("needs_clarification", "failed", "skipped") — missing "error"
      - ("needs_clarification", "failed", "error", "skipped") — correct

    Now all nodes use _should_skip_node(state) which checks the canonical set.

    Usage:
        if _should_skip_node(state):
            return {}
    """
    return state.get("status") in _SKIP_STATUSES
