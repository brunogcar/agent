"""Node: decide — Keep (git commit) or discard (git reset) the experiment.

[v1.0] Compares `current_metric` against `current_best` using the configured
direction ("lower" or "higher"). If improved, commits the change and updates
`current_best`. If worse or equal, discards via `git reset --hard HEAD` (or
`git checkout -- <target_file>`) to restore the last-known-good state.

The decision is logged to the trace regardless of outcome, and the
experiment_history entry's `status` field is set to "keep" or "discard".

Returns a PARTIAL state dict with `current_best` (updated if kept) and
`current_experiment` (annotated with `status` and `commit`).

[v1.3 P0-1] This node now runs BEFORE `log` (was: AFTER). It annotates
`current_experiment` with `status` + `commit` + `metric` so `log` can
write the CORRECT status to the ledger. Also takes over the
`status="running"` + `error=""` reset (was: done by `log`).

[v1.3 P1-1] Treat empty SHA (git commit failed) as discard — don't update
`current_best`. Was: set `status="keep"` with empty commit, which made the
ledger record an ambiguous "keep with no SHA".

[v1.3 P1-4] `_git_reset_hard` safety guard — refuses to reset without an
explicit `project_root` or when `project_root` isn't a git repo. Prevents
accidentally resetting the agent's own working tree.

[v1.6] When `parallel_count > 1`, picks the BEST of the N experiments in
`current_experiments` (skipping any marked `status="failed"` by modify).
The winner's temp-file content is copied to the real `target_file`, then
`git add + commit` records it. All other experiments are annotated
`status="discard"` (with empty commit) so `node_log` writes them to the
ledger as discarded. The temp dir `{project_root}/.autoresearch/parallel/`
is removed (shutil.rmtree(ignore_errors=True)) on every exit path. If NO
experiment improves on `current_best`, all N are discarded and
`current_best` is left unchanged. Cross-run procedural memory (v1.5 N4) is
recorded for each discarded experiment so future runs can avoid the same
dead-ends. When `parallel_count == 1`, the v1.5 single-experiment path
runs unchanged.

[v1.7 N7] Checkpoint on every keep — after `_git_commit` returns a non-empty
SHA (both single-experiment and parallel paths), `save_checkpoint(tid,
"keep", state)` is called so a crashed run can resume from the last-known-
good state via `get_latest(trace_id)`. Non-fatal: checkpoint write failures
are swallowed (try/except) so the experiment loop is never blocked. Discard
paths do NOT checkpoint — only keeps represent a recoverable state worth
resuming from.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState
# [v1.9 A3] Import _atomic_write for the parallel winner copy — was using
# non-atomic real_path.write_text(...) which leaves the target_file empty/
# partial on SIGKILL/OOM mid-write. (minimax Bug #3)
# [v1.10 / Phase A] _atomic_write now lives in core.atomic_write (alias kept
# in modify.py for backward compat).
from core.atomic_write import atomic_write as _atomic_write
# [v1.10 / Phase B] _git_commit + _git_reset_hard extracted to
# tools.git_ops.workflow_helpers. Old local `_git_commit(message, project_root,
# tid, target_file) -> str` is replaced by `commit(project_root, message,
# target_file, tid) -> dict`. We import under the old name `_git_commit_w`
# so the parallel-path call sites can be updated surgically.
from tools.git_ops.workflow_helpers import (
    commit as _git_commit_w,
    reset_hard as _git_reset_hard,
)


def _is_cancelled(tid: str) -> bool:
    """[v1.10 / Phase B] Lazy + safe cancellation check.

    Wraps `workflows.base.is_workflow_cancelled` in a try/except so a broken
    import doesn't crash the node. Returns False on any failure — fail-open
    so a broken cancellation system doesn't halt the experiment loop.
    """
    if not tid:
        return False
    try:
        from workflows.base import is_workflow_cancelled
        return is_workflow_cancelled(tid)
    except Exception:
        return False


def _is_improvement(new: float, best: float, direction: str) -> bool:
    """Return True if `new` is strictly better than `best` given `direction`.

    direction="lower"  → new < best  is an improvement
    direction="higher" → new > best  is an improvement

    Equality is NOT an improvement — we want to discourage the LLM from
    proposing no-op changes that just shuffle code without moving the metric.

    [v1.9 E1] NaN handling — `float('nan')` comparisons are always False in
    Python, so a NaN metric would silently fail both `new < best` and
    `new > best` → returns False (not an improvement). This is the CORRECT
    behavior (a NaN metric means the experiment crashed numerically and
    should be discarded), but it was implicit. The explicit `new != new` check
    (the canonical NaN self-test) documents the intent and guards against a
    future contributor "fixing" the comparison.
    """
    # [v1.9 E1] Explicit NaN check — `new != new` is True only for NaN.
    # Mirrors the implicit behavior (NaN comparisons are always False), but
    # documents the intent: a NaN metric is never an improvement.
    if new != new:  # NaN check (NaN != NaN is the only True case)
        return False
    if direction == "lower":
        return new < best
    elif direction == "higher":
        return new > best
    # Unknown direction — default to "lower is better" (most ML metrics).
    return new < best


# [v1.10 / Phase B] The OLD local _git_commit (raw subprocess.run) +
# _git_reset_hard (raw subprocess.run with toplevel verify) were DELETED —
# both are now imported from tools.git_ops.workflow_helpers. See the imports
# at the top of this file. The _git_commit wrapper below preserves the old
# (message, project_root, tid, target_file) -> str call shape used by the
# parallel + single decide paths.


def _git_commit(message: str, project_root: str, tid: str, target_file: str = "") -> str:
    """[v1.10 / Phase B] Backward-compat wrapper around
    `tools.git_ops.workflow_helpers.commit`.

    Old signature: `(message, project_root, tid, target_file) -> str`.
    New signature: `commit(project_root, message, target_file, tid) -> dict`.

    This wrapper preserves the OLD call shape so the parallel + single
    decide paths don't need to be rewritten — they call `_git_commit(msg,
    project_root, tid, target_file)` and expect a short SHA string (or ""
    on failure). Internally, we adapt to the new dict return.

    Returns the short SHA string, or "" on failure (nothing to commit,
    exception, etc.).
    """
    result = _git_commit_w(project_root, message, target_file, tid)
    if isinstance(result, dict) and result.get("committed"):
        return result.get("sha", "")
    return ""


# [v1.10 / Phase B] _git_reset_hard is imported from tools.git_ops.workflow_helpers
# (see top-of-file imports). The local raw-subprocess definition is DELETED.


def _record_failure_memory(
    proposal: dict,
    metric_name: str,
    current_metric: float,
    current_best: float,
    direction: str,
    tid: str,
    goal: str,
) -> None:
    """[v1.5 N4] Cross-run learning — record a procedural memory on discard.

    Checks if a similar failure has been recorded before (`min_score=0.7`).
    If yes, the failure pattern is already known — just trace a "repeated
    failure pattern detected" log line so operators can spot when the LLM
    keeps hitting the same wall. If no, stores a fresh procedural memory so
    the next run's `node_propose` can recall it (via
    `memory.recall(collections=["procedural"])`) and avoid re-proposing the
    same dead-end.

    Failures are non-fatal — `core.memory_engine.memory` may not be available
    (e.g. in tests, or if ChromaDB is disabled). The whole call is wrapped
    in try/except so a memory-store error never halts the experiment loop.
    [v1.9-V2 / mistral #7] The except block now logs a `tracer.warning`
    (was: silently swallowed via `except Exception: pass`). Operators need
    to know when cross-run learning is disabled so they can debug — a silent
    swallow hides the fact that procedural memory isn't being recorded.
    """
    try:
        from core.memory_engine import memory
        desc = proposal.get("description", "")[:100]
        if not desc:
            return
        existing = memory.recall(
            query=f"autoresearch failed: {desc}",
            collections=["procedural"],
            top_k=1,
            min_score=0.7,
            trace_id=tid,
        )
        if existing:
            tracer.step(tid, "decide", f"repeated failure pattern detected: {desc[:60]}")
        else:
            memory.store_procedural(
                text=(
                    f"autoresearch: proposal '{desc}' did not improve {metric_name} "
                    f"(metric={current_metric}, best={current_best}, direction={direction})"
                ),
                importance=5,
                tags="source:autoresearch,category:failed_experiment",
                trace_id=tid,
                goal=goal,
                outcome="failure",
            )
    except Exception as e:
        # [v1.9-V2 / mistral #7] Surface memory unavailability via a tracer
        # warning (was: silently swallowed via `except Exception: pass`).
        # Operators need to know when cross-run learning is disabled so they
        # can debug — a silent swallow hides the fact that procedural memory
        # isn't being recorded. The behavior is unchanged (feature disabled),
        # just made visible.
        tracer.warning(
            tid, "decide",
            f"memory engine unavailable — cross-run learning disabled: {e}",
        )


def node_decide(state: AutoresearchState) -> dict:
    """Keep (commit) or discard (reset) the current experiment.

    Returns a partial state dict with:
      current_best      — updated if the experiment was kept
      current_experiment — annotated with {status, commit, metric}
      status            — reset to "running" (v1.3 P0-1: was log's job)
      error             — cleared (v1.3 P0-1: was log's job)

    The status reset is the loop's recovery point — without it, the next
    iteration's `node_run_experiment` would skip the run (thinking a prior
    node failed). This reset moved from `log` to `decide` in v1.3 P0-1
    because `decide` now runs BEFORE `log`.

    [v1.6] When `parallel_count > 1`, picks the best of N experiments.
    The winner's temp file is copied to the real `target_file`, then git
    committed. Losers are annotated `status="discard"`. The temp dir is
    cleaned up on every exit path (success, no-improvement, prior-failure).
    """
    tid = state.get("trace_id", "")
    project_root = state.get("project_root", "")
    direction = state.get("metric_direction", "") or cfg.autoresearch_metric_direction
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    goal = state.get("goal", "")  # [v1.5 N4] forwarded to memory.store_procedural
    parallel_count = int(state.get("parallel_count", 1) or 1)

    # [v1.10 / Phase B] Cancellation check — before the git commit. If cancelled,
    # return status="failed" so the loop exits. In the parallel path, still
    # clean up the temp dir (the try/finally below handles that).
    if _is_cancelled(tid):
        tracer.step(tid, "decide", "workflow cancelled — skipping git commit")
        # Parallel path: clean up temp dir before returning.
        if parallel_count > 1:
            base_path = Path(project_root) if project_root else Path(".")
            parallel_dir = base_path / ".autoresearch" / "parallel"
            try:
                shutil.rmtree(parallel_dir, ignore_errors=True)
            except Exception:
                pass
        return {
            "status": "failed",
            "errors": ["Workflow cancelled"],
            "error": "Workflow cancelled",
        }

    # ── [v1.6] Parallel path: pick best of N, copy winner, cleanup ─────────
    if parallel_count > 1:
        from pathlib import Path

        proposals = [dict(p) for p in (state.get("current_experiments", []) or [])]
        metrics = list(state.get("current_metrics", []) or [])
        current_best = state.get("current_best", 0.0)
        target_file = state.get("target_file", "")
        base_path = Path(project_root) if project_root else Path(".")
        parallel_dir = base_path / ".autoresearch" / "parallel"

        # [v1.9-V2 / mistral #3] Wrap the ENTIRE parallel path body in
        # try/finally with `shutil.rmtree(parallel_dir)` in `finally`. The
        # previous code had TWO inline `shutil.rmtree(parallel_dir, ...)` calls
        # — one on the winner-takes-all path + one on the no-improvement path.
        # Both ran on the SUCCESS paths only; an exception raised BETWEEN them
        # (e.g. `_git_commit` raised) leaked the temp dir. The `finally` block
        # ALWAYS runs — on return from inside the try AND on exception — so the
        # temp dir is cleaned up regardless of how the parallel path exits.
        # The inline rmtree calls are removed (replaced by this single finally).
        try:
            # Pad metrics to len(proposals) so zip() stays aligned.
            while len(metrics) < len(proposals):
                metrics.append(0.0)

            # Find the best experiment — the one that maximally improves on
            # current_best (greedy: each iteration lowers/raises the bar).
            # Skip proposals already marked "failed" by modify (empty content /
            # dedup / path / protected) — they didn't even run.
            best_idx = None
            best_metric = current_best
            for i, (proposal, metric) in enumerate(zip(proposals, metrics)):
                if proposal.get("status") == "failed":
                    continue
                if _is_improvement(metric, best_metric, direction):
                    best_metric = metric
                    best_idx = i

            if best_idx is not None:
                # Copy the winner's content to the real target_file.
                winner_path = parallel_dir / str(best_idx) / target_file
                real_path = base_path / target_file
                if winner_path.exists():
                    try:
                        real_path.parent.mkdir(parents=True, exist_ok=True)
                        # [v1.9 A3] Use _atomic_write (tempfile + os.fsync +
                        # os.replace) — was: real_path.write_text(...) which is
                        # non-atomic. SIGKILL/OOM mid-write left target_file
                        # empty/partial → next node_propose reads "" → chaos.
                        # (minimax Bug #3)
                        _atomic_write(
                            real_path,
                            winner_path.read_text(encoding="utf-8"),
                        )
                    except Exception as e:
                        tracer.warning(
                            tid, "decide",
                            f"failed to copy winner {best_idx} to {real_path}: {e}",
                        )

                # Commit the winner.
                winner = proposals[best_idx]
                commit_msg = (
                    f"autoresearch: iter {winner.get('iteration', '?')} — "
                    f"{winner.get('description', '')[:80]}\n\n"
                    f"{metric_name}: {metrics[best_idx]} (was {current_best}, "
                    f"direction={direction}) [parallel best of {len(proposals)}]"
                )
                sha = _git_commit(commit_msg, project_root, tid, target_file)

                # Annotate all proposals — winner="keep" (or "discard" if commit
                # failed), others="discard". Mirrors v1.5 P1-1 empty-SHA handling.
                for i, proposal in enumerate(proposals):
                    proposal["metric"] = metrics[i]
                    if i == best_idx and sha:
                        proposal["status"] = "keep"
                        proposal["commit"] = sha
                    else:
                        proposal["status"] = "discard"
                        proposal["commit"] = ""
                        # [v1.5 N4] Record procedural memory for each discarded
                        # experiment (parallel mode — N discards per iteration).
                        # Skip the winner when commit failed (i == best_idx and
                        # not sha) — recording it would mislead future runs.
                        # [v1.9 A1] Gate on `not _is_improvement(...)` — a loser
                        # that DID improve over the OUTER current_best (but lost
                        # to the winner) must NOT be recorded as a failure.
                        # Pre-v1.9, every loser got _record_failure_memory called
                        # with current_best = the OUTER (pre-iteration) best, so
                        # a loser with metric 0.45 (better than outer 0.5) was
                        # stored as "did not improve" → future runs would avoid
                        # a perfectly valid change. (minimax Bug #1)
                        if i != best_idx and not _is_improvement(
                            metrics[i], current_best, direction
                        ):
                            _record_failure_memory(
                                proposal, metric_name, metrics[i],
                                current_best, direction, tid, goal,
                            )

                new_best = metrics[best_idx] if sha else current_best
                tracer.step(
                    tid, "decide",
                    f"parallel: KEPT {sha or '(no commit)'} (idx={best_idx}, "
                    f"{metric_name}={metrics[best_idx]} vs best={current_best})",
                )

                # [v1.7 N7] Checkpoint on every keep (parallel path) — only when
                # the winner was actually committed (sha truthy). Mirrors the
                # single-experiment path: a crashed run resumes from the last
                # known good parallel-keep via get_latest(trace_id). Non-fatal.
                if sha:
                    try:
                        from core.observability.checkpoint import save_checkpoint
                        save_checkpoint(tid, "keep", {
                            **state,
                            "current_best": new_best,
                            "current_experiment": proposals[best_idx],
                            "experiment_count": state.get("experiment_count", 0),
                        })
                    except Exception:
                        pass  # Non-fatal — checkpoint failure shouldn't block the loop

                return {
                    "current_experiments": proposals,
                    "current_experiment": proposals[best_idx],  # backward compat
                    "current_best": new_best,
                    "status": "running",
                    "error": "",
                }

            # No improvement — discard all N. Temp dir cleaned up by finally.
            tracer.step(
                tid, "decide",
                f"parallel: no improvement across {len(proposals)} experiments — discarding all",
            )
            for i, proposal in enumerate(proposals):
                proposal["metric"] = metrics[i]
                proposal["status"] = "discard"
                proposal["commit"] = ""
                # [v1.5 N4] Record procedural memory for each discarded experiment.
                # [v1.9 A1] Gate on `not _is_improvement(...)` — even on the
                # no-improvement path, a proposal whose metric IS strictly better
                # than the OUTER current_best (rare but possible when none beat
                # best_metric which started equal to current_best) must NOT be
                # recorded as a failure. (minimax Bug #1)
                if not _is_improvement(metrics[i], current_best, direction):
                    _record_failure_memory(
                        proposal, metric_name, metrics[i],
                        current_best, direction, tid, goal,
                    )

            return {
                "current_experiments": proposals,
                "current_experiment": proposals[0] if proposals else {},
                "current_best": current_best,
                "status": "running",
                "error": "",
            }
        finally:
            # [v1.9-V2 / mistral #3] ALWAYS clean up the temp dir — runs on
            # return from inside the try AND on exception. The previous inline
            # rmtree calls only ran on success paths; an exception between them
            # (e.g. _git_commit raised mid-block) leaked the temp dir.
            shutil.rmtree(parallel_dir, ignore_errors=True)

    # ── v1.5 single-experiment path (unchanged) ────────────────────────────
    proposal = dict(state.get("current_experiment", {}) or {})
    iteration = proposal.get("iteration", state.get("experiment_count", 0) + 1)
    description = proposal.get("description", "")
    current_metric = state.get("current_metric", 0.0)
    current_best = state.get("current_best", 0.0)

    # If a prior node (modify/evaluate) failed, always discard.
    if state.get("status") == "failed":
        tracer.step(tid, "decide", f"iter {iteration}: discarding (prior failure)")
        _git_reset_hard(project_root, tid)
        # [v1.5 N4] Cross-run learning — record procedural memory on discard
        # so future runs can avoid re-proposing this dead-end.
        _record_failure_memory(
            proposal, metric_name, current_metric, current_best, direction, tid, goal,
        )
        proposal["status"] = "discard"
        proposal["commit"] = ""
        proposal["metric"] = current_metric
        return {
            "current_experiment": proposal,
            "current_best": current_best,
            # [v1.3 P0-1] status reset moved here from log.py
            "status": "running",
            "error": "",
        }

    improved = _is_improvement(current_metric, current_best, direction)
    if not improved:
        tracer.step(
            tid, "decide",
            f"iter {iteration}: discarding "
            f"({metric_name}={current_metric} vs best={current_best}, direction={direction})",
        )
        _git_reset_hard(project_root, tid)
        # [v1.5 N4] Cross-run learning — record procedural memory on discard
        # so future runs can avoid re-proposing this dead-end.
        _record_failure_memory(
            proposal, metric_name, current_metric, current_best, direction, tid, goal,
        )
        proposal["status"] = "discard"
        proposal["commit"] = ""
        proposal["metric"] = current_metric
        return {
            "current_experiment": proposal,
            "current_best": current_best,
            # [v1.3 P0-1] status reset moved here from log.py
            "status": "running",
            "error": "",
        }

    # Improvement — commit and update current_best
    commit_msg = (
        f"autoresearch: iter {iteration} — {description[:80]}\n\n"
        f"{metric_name}: {current_metric} (was {current_best}, direction={direction})"
    )
    sha = _git_commit(commit_msg, project_root, tid, state.get("target_file", ""))
    # [v1.3 P1-1] Treat empty SHA (commit failed) as discard — don't update
    # current_best. Was: set status="keep" with empty commit, which made the
    # ledger record an ambiguous "keep with no SHA".
    if not sha:
        tracer.warning(
            tid, "decide",
            f"iter {iteration}: commit failed — discarding despite improvement "
            f"({metric_name}={current_metric} vs best={current_best})",
        )
        _git_reset_hard(project_root, tid)
        proposal["status"] = "discard"
        proposal["commit"] = ""
        proposal["metric"] = current_metric
        return {
            "current_experiment": proposal,
            "current_best": current_best,
            # [v1.3 P0-1] status reset moved here from log.py
            "status": "running",
            "error": "",
        }

    tracer.step(
        tid, "decide",
        f"iter {iteration}: KEPT {sha} "
        f"({metric_name}={current_metric}, was={current_best}, direction={direction})",
    )
    proposal["status"] = "keep"
    proposal["commit"] = sha
    proposal["metric"] = current_metric

    # [v1.7 N7] Checkpoint on every keep — so a crashed run can resume from
    # the last-known-good state via get_latest(trace_id). Non-fatal: a
    # checkpoint write failure must NOT block the experiment loop. The state
    # saved here includes the updated current_best + current_experiment so
    # node_setup's resume path can skip the baseline (current_best > 0.0)
    # and node_propose gets the most recent keep in experiment_history (via
    # the ledger reload in _load_history_from_ledger).
    try:
        from core.observability.checkpoint import save_checkpoint
        save_checkpoint(tid, "keep", {
            **state,
            "current_best": current_metric,
            "current_experiment": proposal,
            "experiment_count": state.get("experiment_count", 0),
        })
    except Exception:
        pass  # Non-fatal — checkpoint failure shouldn't block the loop

    return {
        "current_experiment": proposal,
        "current_best": current_metric,
        # [v1.3 P0-1] status reset moved here from log.py
        "status": "running",
        "error": "",
    }
