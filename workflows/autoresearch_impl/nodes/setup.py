"""Node: setup — Create branch, init results ledger, run baseline experiment.

[v1.0] Setup phase of the autoresearch loop:
  1. Create git branch `autoresearch/{tag}` (tag from date)
  2. Initialize results.tsv with header
  3. Run baseline experiment (target_file as-is)
  4. Record baseline metric — this becomes the initial current_best

The baseline is the reference point every proposed experiment is compared
against. If a proposed change makes the metric worse, we git-reset back to
the baseline (or last-kept commit).

Returns a PARTIAL state dict (LangGraph pattern — only changed keys).

[v1.3 P2-1] `_run_experiment_subprocess` removed — replaced with the shared
`workflows.autoresearch_impl.helpers.run_target_subprocess`. The two
originals (in setup.py + run_experiment.py) had drifted in subtle ways;
consolidating eliminates that drift.

[v1.7 N3] Resume support — when `state["resume"]` is True AND `state["branch"]`
is non-empty, branch creation is skipped (the prior run's branch is reused).
When `state["current_best"]` is also > 0.0, the baseline run is skipped too,
and `experiment_history` is reloaded from `results.tsv` (via the new
`_load_history_from_ledger` helper) so `node_propose` has the prior
experiments in context. When `resume=False` (default), behavior is exactly
v1.6 (new branch, run baseline, fresh ledger).

[v1.9] Hardening — 3 changes:
  (A2) The TSV header now has a 6th `content_hash` column so dedup survives
  resume. `_load_history_from_ledger` parses 6 cols (legacy 5-col ledgers
  load with `content_hash=""`). Corrupt rows (<5 cols) now log a
  `tracer.warning` instead of being silently skipped (deepseek P2 2.2).
  (B1) On resume, `consecutive_discards` + `consecutive_no_improvement` are
  recomputed by scanning the tail of the reloaded history (qwen P1-2).
  `seen_hashes` is populated from the reloaded history's `content_hash`
  values (deduped) so cross-run dedup survives the 100-entry history cap.
  (B2) `node_setup` cleans up any stale `{project_root}/.autoresearch/parallel/`
  dir left by a prior crashed run BEFORE creating a new branch (qwen P1-3).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState
from workflows.autoresearch_impl.helpers import (
    extract_metric as _extract_metric_from_output,
    run_target_subprocess as _run_experiment_subprocess,
)
# [v1.10 / Phase B] _git_create_branch extracted to tools.git_ops.workflow_helpers
# (as `create_branch`). Old signature `(branch, project_root, tid) -> bool`;
# new signature `(project_root, branch, tid) -> bool` (project_root FIRST).
# The local definition was deleted — call site updated to the new arg order.
from tools.git_ops.workflow_helpers import create_branch as _git_create_branch

# v1.2.1 (P1-2): _extract_metric_from_output now imported from helpers.py
# v1.3 (P2-1): _run_experiment_subprocess now imported from helpers.py


# Header for results.tsv. Tab-separated so it's easy to grep/awk/cut.
# [v1.9 A2] Added a 6th `content_hash` column so dedup survives resume.
# Legacy 5-col ledgers load with content_hash="" (no dedup against old rows).
_RESULTS_HEADER = "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"


def _load_history_from_ledger(results_path: str, tid: str = "") -> list[dict]:
    """[v1.7 N3 / v1.9 A2] Parse results.tsv back into experiment_history dicts.

    Each ledger row is `iteration<TAB>commit<TAB>metric<TAB>status<TAB>
    description[<TAB>content_hash]` — the 6th `content_hash` column was added
    in v1.9 A2 so dedup survives resume. Legacy 5-col ledgers load with
    `content_hash=""` (no dedup against old rows — backward compatible).

    The header line starts with `iteration<TAB>` and is skipped. Rows with
    fewer than 5 columns (corrupt / partial writes) are SKIPPED with a
    `tracer.warning` that includes the line number + content (deepseek P2 2.2
    — was: silently dropped, operators never knew). Non-fatal — any parse
    error returns an empty list (the loop continues with no history; the LLM
    just won't see prior experiments on the first resumed iteration).

    The reloaded history is what `node_propose` reads (last 20 entries) so the
    LLM has context for the next proposal. Without this reload, a resumed run
    would start with `experiment_history=[]` and the LLM would re-propose
    experiments that were already tried.
    """
    history: list[dict] = []
    try:
        p = Path(results_path)
        if not p.exists():
            return []
        for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if line.startswith("iteration\t") or not line.strip():
                continue  # header or empty line
            parts = line.split("\t")
            if len(parts) < 5:
                # [v1.9 deepseek P2 2.2] Warn on corrupt rows instead of
                # silently skipping — operators need to know data was lost.
                tracer.warning(
                    tid, "setup",
                    f"results.tsv line {line_no} has {len(parts)} columns "
                    f"(expected >=5) — skipping: {line[:80]!r}",
                )
                continue
            history.append({
                "iteration": int(parts[0]) if parts[0].isdigit() else 0,
                "commit": parts[1],
                "metric": float(parts[2]) if parts[2] else 0.0,
                "status": parts[3],
                "description": parts[4],
                # [v1.9 A2] 6th column — content_hash. Missing on legacy
                # 5-col ledgers → "" (no dedup against old rows).
                "content_hash": parts[5] if len(parts) >= 6 else "",
            })
    except Exception as e:
        tracer.warning(tid, "setup", f"_load_history_from_ledger parse error: {e}")
    return history


def _cleanup_stale_parallel_dir(project_root: str, tid: str) -> None:
    """[v1.9 B2] Remove any stale `{project_root}/.autoresearch/parallel/` dir.

    The parallel mode writes N temp files under this dir per iteration;
    node_decide cleans it up via `shutil.rmtree(ignore_errors=True)` on every
    exit path. BUT if the process is killed (SIGKILL, OOM, power loss) BEFORE
    node_decide runs, the dir is leaked. Each leaked dir contains a full copy
    of target_file + experiment output — accumulating disk usage across many
    crashed runs.

    This cleanup runs at the START of `node_setup` (BEFORE creating a new
    branch) so a fresh run starts with a clean parallel dir. Best-effort
    `ignore_errors=True` + trace — a permission error doesn't crash setup.
    Mirrors the `_cleanup_old_autocode_runs` pattern in autocode_impl/helpers.py.
    """
    if not project_root:
        return
    try:
        parallel_dir = Path(project_root) / ".autoresearch" / "parallel"
        if parallel_dir.exists():
            shutil.rmtree(parallel_dir, ignore_errors=True)
            tracer.step(
                tid, "setup",
                f"cleaned up stale parallel dir from prior run: {parallel_dir}",
            )
    except Exception as e:
        tracer.warning(tid, "setup", f"parallel dir cleanup failed (non-fatal): {e}")


def _recompute_convergence_counters(
    history: list[dict],
    current_best: float,
    direction: str,
) -> tuple[int, int]:
    """[v1.9 B1] Recompute consecutive_discards + consecutive_no_improvement.

    Scans the tail of `history` (most-recent-first) counting:
      - consecutive_discards: trailing entries with status="discard".
      - consecutive_no_improvement: trailing entries whose `metric` is NOT
        strictly better than `current_best` per `direction`.

    Used on resume so the convergence detector fires correctly. Pre-v1.9,
    `consecutive_discards` was reset to 0 on resume — if the last 4 before
    crash were all discards, the detector needed 4+10=14 total instead of 10.
    (qwen P1-2)
    """
    consecutive_discards = 0
    for entry in reversed(history):
        if entry.get("status", "") == "discard":
            consecutive_discards += 1
        else:
            break  # any non-discard breaks the run
    consecutive_no_improvement = 0
    for entry in reversed(history):
        metric = entry.get("metric", 0.0)
        # Inline the direction logic to avoid a circular import from decide.py.
        if direction == "higher":
            improved = metric > current_best
        else:
            improved = metric < current_best
        if not improved:
            consecutive_no_improvement += 1
        else:
            break
    return consecutive_discards, consecutive_no_improvement


def _populate_seen_hashes_from_history(history: list[dict]) -> list[str]:
    """[v1.9 C4] Extract deduped content_hash list from reloaded history.

    Used on resume so cross-run dedup survives the 100-entry history cap.
    Returns a list (NOT a set — preserve insertion order, dedupe via a
    seen-set). Empty/"" hashes are skipped (failed-proposal placeholders).
    """
    seen: set[str] = set()
    hashes: list[str] = []
    for entry in history:
        h = entry.get("content_hash", "")
        if h and h not in seen:
            seen.add(h)
            hashes.append(h)
    return hashes


def node_setup(state: AutoresearchState) -> dict:
    """Setup phase: branch, ledger, baseline.

    Returns partial state dict with:
      branch, results_path, baseline_metric, current_best, experiment_count,
      status (or error on failure).
    """
    tid = state.get("trace_id", "")
    project_root = state.get("project_root", "") or str(getattr(cfg, "workspace_root", ""))
    target_file = state.get("target_file", "") or cfg.autoresearch_target_file
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    time_budget = state.get("time_budget", cfg.autoresearch_time_budget)

    # [v1.9 B2] Clean up any stale parallel dir from a prior crashed run
    # BEFORE doing anything else. node_decide cleans the dir up on every exit
    # path, but a SIGKILL/OOM before decide leaves it leaked. Best-effort.
    _cleanup_stale_parallel_dir(project_root, tid)

    # [v1.7 N3] Resume awareness — caller passes resume=True when continuing
    # from a prior run (via run_workflow(resume=True)). When resuming AND
    # the caller supplied an existing branch + current_best, we skip branch
    # creation + baseline and reload experiment_history from results.tsv.
    is_resume = bool(state.get("resume", False))

    # 1. Branch name + creation
    # [v1.7 N3] Skip branch creation if resuming with an existing branch.
    if is_resume and state.get("branch", ""):
        branch = state.get("branch", "")
        tracer.step(tid, "setup", f"resume: using existing branch {branch} (skipping creation)")
    else:
        tag = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch = state.get("branch", "") or f"autoresearch/{tag}"
        # [v1.10 / Phase B] _git_create_branch signature changed: now
        # `create_branch(project_root, branch, tid)` (project_root FIRST).
        if not _git_create_branch(project_root, branch, tid):
            # Non-fatal: experiments can still proceed on the current branch,
            # but the safety net (revert via branch) is gone. Log and continue.
            tracer.warning(tid, "setup", "branch creation failed — continuing on current branch")

    # 2. Results ledger (results.tsv)
    results_path = state.get("results_path", "") or str(
        Path(project_root) / "results.tsv" if project_root else "results.tsv"
    )
    try:
        # Only write the header if the file doesn't already exist (resume case)
        rpath = Path(results_path)
        if not rpath.exists():
            rpath.parent.mkdir(parents=True, exist_ok=True)
            rpath.write_text(_RESULTS_HEADER, encoding="utf-8")
            tracer.step(tid, "setup", f"initialized ledger @ {results_path}")
    except Exception as e:
        tracer.warning(tid, "setup", f"ledger init failed: {e}")

    # [v1.7 N3] Skip baseline if resuming with existing current_best — the
    # prior run already established the baseline; re-running it wastes time
    # (and could change current_best if the target_file is non-deterministic).
    # Reload experiment_history from results.tsv so node_propose has context.
    if is_resume and state.get("current_best", 0.0) > 0.0:
        tracer.step(
            tid, "setup",
            f"resume: skipping baseline (current_best={state.get('current_best')})",
        )
        history = _load_history_from_ledger(results_path, tid)
        experiment_count = len(history)
        tracer.step(
            tid, "setup",
            f"resume: reloaded {experiment_count} experiments from ledger",
        )
        # [v1.9 B1] Recompute convergence counters from the reloaded history
        # tail — pre-v1.9 these were reset to 0 on resume, so the convergence
        # detector wouldn't fire until N MORE discards happened (qwen P1-2).
        direction = state.get("metric_direction", "") or cfg.autoresearch_metric_direction
        consecutive_discards, consecutive_no_improvement = _recompute_convergence_counters(
            history, state.get("current_best", 0.0), direction,
        )
        # [v1.9 C4] Populate seen_hashes from the reloaded history so cross-
        # run dedup survives the 100-entry history cap (qwen P2-1).
        seen_hashes = _populate_seen_hashes_from_history(history)
        return {
            "branch": branch,
            "results_path": results_path,
            "experiment_count": experiment_count,
            "baseline_metric": state.get("baseline_metric", 0.0),
            "current_best": state.get("current_best", 0.0),
            "experiment_history": history,
            "consecutive_discards": consecutive_discards,
            "consecutive_no_improvement": consecutive_no_improvement,
            "seen_hashes": seen_hashes,
            "status": "running",
        }

    # 3. Baseline experiment — run the target_file as-is
    tracer.step(tid, "setup", f"running baseline experiment: {target_file}")
    # v1.3 (P2-1): Use the shared helper — was a local _run_experiment_subprocess
    # with slightly different exception handling.
    baseline_output = _run_experiment_subprocess(target_file, project_root, time_budget)
    baseline_metric = _extract_metric_from_output(baseline_output, metric_name)
    if baseline_metric is None:
        # Baseline failed — we can't measure improvement. Mark as failed so
        # the operator knows to fix the target_file before re-running.
        tracer.error(tid, "setup", f"baseline metric '{metric_name}' not found in output")
        return {
            "branch": branch,
            "results_path": results_path,
            "experiment_count": 0,
            "baseline_metric": 0.0,
            "current_best": 0.0,
            "experiment_output": baseline_output,
            "current_metric": 0.0,
            "status": "failed",
            "error": f"baseline metric '{metric_name}' not found in target_file output",
        }

    tracer.step(tid, "setup", f"baseline {metric_name}={baseline_metric}")
    return {
        "branch": branch,
        "results_path": results_path,
        "experiment_count": 0,
        "baseline_metric": baseline_metric,
        "current_best": baseline_metric,
        "experiment_output": baseline_output,
        "current_metric": baseline_metric,
        "status": "running",
    }
