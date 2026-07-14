"""Node: decide — Keep (git commit) or discard (git reset) the experiment.

[v1.0] Compares `current_metric` against `current_best` using the configured
direction ("lower" or "higher"). If improved, commits the change and updates
`current_best`. If worse or equal, discards via `git reset --hard HEAD` (or
`git checkout -- <target_file>`) to restore the last-known-good state.

The decision is logged to the trace regardless of outcome, and the
experiment_history entry's `status` field is set to "keep" or "discard".

Returns a PARTIAL state dict with `current_best` (updated if kept) and
`current_experiment` (annotated with `status` and `commit`).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


def _is_improvement(new: float, best: float, direction: str) -> bool:
    """Return True if `new` is strictly better than `best` given `direction`.

    direction="lower"  → new < best  is an improvement
    direction="higher" → new > best  is an improvement

    Equality is NOT an improvement — we want to discourage the LLM from
    proposing no-op changes that just shuffle code without moving the metric.
    """
    if direction == "lower":
        return new < best
    elif direction == "higher":
        return new > best
    # Unknown direction — default to "lower is better" (most ML metrics).
    return new < best


def _git_commit(message: str, project_root: str, tid: str, target_file: str = "") -> str:
    """Stage the target_file and commit. Returns the short commit SHA.

    Uses subprocess directly (not the git tool) to keep this node self-
    contained — the git tool's commit action goes through compression and
    tracing that adds noise to the experiment loop.

    v1.2.1 (P3-1): git add <target_file> instead of git add -A (was staging
    ALL files — could commit unexpected artifacts from the experiment subprocess).

    Returns "" if the commit failed (caller treats as discard).
    """
    try:
        # v1.2.1 (P3-1): Stage only the target_file, not all changes.
        add_cmd = ["git", "add", target_file] if target_file else ["git", "add", "-A"]
        subprocess.run(
            add_cmd,
            cwd=project_root or None,
            capture_output=True,
            timeout=15,
        )
        r = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_root or None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            tracer.warning(tid, "decide", f"git commit failed: {r.stderr.strip()[:200]}")
            return ""
        # Get the short SHA of the new commit
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception as e:
        tracer.warning(tid, "decide", f"git commit exception: {e}")
        return ""


def _git_reset_hard(project_root: str, tid: str) -> bool:
    """Discard uncommitted changes via `git reset --hard HEAD` + `git clean -fd`.

    Used when an experiment made the metric worse (or failed to parse) — we
    want to restore the working tree to the last-known-good state so the
    next experiment starts from a clean baseline.
    """
    try:
        subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=project_root or None,
            capture_output=True,
            timeout=15,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=project_root or None,
            capture_output=True,
            timeout=15,
        )
        return True
    except Exception as e:
        tracer.warning(tid, "decide", f"git reset exception: {e}")
        return False


def node_decide(state: AutoresearchState) -> dict:
    """Keep (commit) or discard (reset) the current experiment.

    Returns a partial state dict with:
      current_best     — updated if the experiment was kept
      current_experiment — annotated with {status, commit}
    """
    tid = state.get("trace_id", "")
    project_root = state.get("project_root", "")
    direction = state.get("metric_direction", "") or cfg.autoresearch_metric_direction
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name

    proposal = dict(state.get("current_experiment", {}) or {})
    iteration = proposal.get("iteration", state.get("experiment_count", 0) + 1)
    description = proposal.get("description", "")
    current_metric = state.get("current_metric", 0.0)
    current_best = state.get("current_best", 0.0)

    # If a prior node (modify/evaluate) failed, always discard.
    if state.get("status") == "failed":
        tracer.step(tid, "decide", f"iter {iteration}: discarding (prior failure)")
        _git_reset_hard(project_root, tid)
        proposal["status"] = "discard"
        proposal["commit"] = ""
        proposal["metric"] = current_metric
        return {
            "current_experiment": proposal,
            "current_best": current_best,
        }

    improved = _is_improvement(current_metric, current_best, direction)
    if not improved:
        tracer.step(
            tid, "decide",
            f"iter {iteration}: discarding "
            f"({metric_name}={current_metric} vs best={current_best}, direction={direction})",
        )
        _git_reset_hard(project_root, tid)
        proposal["status"] = "discard"
        proposal["commit"] = ""
        proposal["metric"] = current_metric
        return {
            "current_experiment": proposal,
            "current_best": current_best,
        }

    # Improvement — commit and update current_best
    commit_msg = (
        f"autoresearch: iter {iteration} — {description[:80]}\n\n"
        f"{metric_name}: {current_metric} (was {current_best}, direction={direction})"
    )
    sha = _git_commit(commit_msg, project_root, tid, state.get("target_file", ""))
    tracer.step(
        tid, "decide",
        f"iter {iteration}: KEPT {sha} "
        f"({metric_name}={current_metric}, was={current_best}, direction={direction})",
    )
    proposal["status"] = "keep"
    proposal["commit"] = sha
    proposal["metric"] = current_metric
    return {
        "current_experiment": proposal,
        "current_best": current_metric,
    }
