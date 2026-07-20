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
"""
from __future__ import annotations

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

# v1.2.1 (P1-2): _extract_metric_from_output now imported from helpers.py
# v1.3 (P2-1): _run_experiment_subprocess now imported from helpers.py


# Header for results.tsv. Tab-separated so it's easy to grep/awk/cut.
# Columns: iteration, commit, metric, status, description
_RESULTS_HEADER = "iteration\tcommit\tmetric\tstatus\tdescription\n"


def _load_history_from_ledger(results_path: str) -> list[dict]:
    """[v1.7 N3] Parse results.tsv back into experiment_history dicts for resume.

    Each ledger row is `iteration\\tcommit\\tmetric\\tstatus\\tdescription`.
    The header line starts with `iteration\\t` and is skipped. Rows with fewer
    than 5 columns (corrupt / partial writes) are skipped. Non-fatal — any
    parse error returns an empty list (the loop continues with no history;
    the LLM just won't see prior experiments on the first resumed iteration).

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
        for line in p.read_text(encoding="utf-8").strip().split("\n"):
            if line.startswith("iteration\t") or not line.strip():
                continue  # header or empty line
            parts = line.split("\t")
            if len(parts) >= 5:
                history.append({
                    "iteration": int(parts[0]) if parts[0].isdigit() else 0,
                    "commit": parts[1],
                    "metric": float(parts[2]) if parts[2] else 0.0,
                    "status": parts[3],
                    "description": parts[4],
                })
    except Exception:
        pass  # Non-fatal — resume continues with empty history on parse error
    return history


def _git_create_branch(branch: str, project_root: str, tid: str) -> bool:
    """Create and checkout a git branch for experiments.

    Uses the git tool's checkout_new action (matches autocode's _git_create_branch
    pattern). Falls back to checkout_branch if the branch already exists.

    Returns True on success, False on failure.
    """
    from tools.git import git
    try:
        r = git(action="checkout_new", target=branch, root=project_root)
        if r.get("status") == "switched":
            tracer.step(tid, "setup", f"created branch {branch} @ {project_root}")
            return True
        error = (r.get("error", "") or "").lower()
        if "already exists" in error:
            r = git(action="checkout_branch", target=branch, root=project_root)
            if r.get("status") == "switched":
                tracer.step(tid, "setup", f"switched to existing branch {branch} @ {project_root}")
                return True
        tracer.step(tid, "setup", f"branch create failed: {r.get('error', 'unknown')}")
        return False
    except Exception as e:
        tracer.step(tid, "setup", f"branch create exception: {e}")
        return False


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
        if not _git_create_branch(branch, project_root, tid):
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
        history = _load_history_from_ledger(results_path)
        experiment_count = len(history)
        tracer.step(
            tid, "setup",
            f"resume: reloaded {experiment_count} experiments from ledger",
        )
        return {
            "branch": branch,
            "results_path": results_path,
            "experiment_count": experiment_count,
            "baseline_metric": state.get("baseline_metric", 0.0),
            "current_best": state.get("current_best", 0.0),
            "experiment_history": history,
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
