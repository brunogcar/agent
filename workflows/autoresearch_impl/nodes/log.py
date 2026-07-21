"""Node: log — Append the experiment result to results.tsv and history.

[v1.0] Appends a single tab-separated row to the results ledger and pushes
a corresponding entry into `experiment_history` so the propose node can see
the full context on the next iteration.

Row format (matches the header written by setup.py):
    iteration\tcommit\tmetric\tstatus\tdescription

The ledger is the human-readable audit trail — operators can `tail -f
results.tsv` while the loop runs to watch progress. The in-memory
`experiment_history` is what the LLM sees when proposing the next change.

[v1.3 P0-1] This node now runs AFTER `decide` (was: BEFORE). `decide`
annotates `current_experiment` with `status="keep"|"discard"` + `commit=sha`
+ `metric=current_metric` before this node reads it. The ledger now records
the CORRECT status — previously it ALWAYS recorded "discard" because log
read `proposal.get("status", "discard")` before decide had set it.

[v1.3 P0-1] This node NO LONGER resets `status` to `"running"` — that
responsibility moved to `decide` (which runs first in the new order, so
its reset propagates to the next iteration's propose). If log reset
status, it would clobber decide's reset and break the contract.

[v1.3 P2-3] `experiment_history` is capped at 100 entries (most recent)
to prevent state bloat on long overnight runs.

[v1.4 N8] Each history entry now includes `content_hash` (md5 of the
proposal's `new_content`, set by `node_modify`) so `node_modify` can dedup
future proposals against it. Ledger row format is unchanged (hash lives
only in the in-memory history — operators don't need it in `results.tsv`).

[v1.6] When `parallel_count > 1`, appends N rows to the ledger (one per
experiment in `current_experiments`) and N entries to
`experiment_history`. `experiment_count` increments by N. Both
`current_experiments` (plural) and `current_experiment` (singular) are
cleared for the next iteration. When `parallel_count == 1`, the v1.5
single-row path runs unchanged.

[v1.9] Hardening — 4 changes:
  (A2) The TSV row now has a 6th `content_hash` column (was: in-memory only).
  This survives resume — `_load_history_from_ledger` parses it back so dedup
  works across crashed/restarted runs. (minimax Bug #2)
  (C1) The parallel path now batches all N rows into a SINGLE `open("a")`
  call (was: N separate calls) — atomic on POSIX for writes < PIPE_BUF=4096,
  reduces syscall overhead, and prevents interleaving on Windows. The single
  path adds `f.flush()` + `os.fsync(f.fileno())` before close for crash-safety.
  (C4) Each new content_hash is appended to `state["seen_hashes"]` (deduped,
  capped at 1000) so cross-run dedup survives the 100-entry history cap.
  (qwen P2-1)
  (D5) `iteration_count` is incremented by 1 per iteration (NOT by N — it
  counts iterations, not experiments). `node_reflect` now fires on
  `iteration_count % interval == 0` so reflect actually fires in parallel
  mode (pre-v1.9, `experiment_count` jumped by N=4 each iter and never hit
  a multiple of 5 → reflect NEVER fired). (minimax Risk #4)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


def _append_to_ledger(results_path: str, row: str, tid: str = "") -> None:
    """Append a single row (or a batch of rows concatenated into `row`) to results.tsv.

    Uses `open(..., "a")` with `f.flush()` + `os.fsync(f.fileno())` before
    close — [v1.9 C1] the fsync forces bytes to disk so a crash mid-write
    doesn't leave a partial row. The row is expected to already be
    tab-separated and end with a newline. For the parallel path, callers
    concatenate all N rows into a single `row` string and call this ONCE —
    atomic on POSIX for writes < PIPE_BUF=4096 and prevents interleaving
    on Windows. (mimo C3, qwen P2-5)
    """
    try:
        p = Path(results_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(row)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        # Non-fatal — the in-memory history is the source of truth for the
        # LLM; the ledger is for human audit. Log and continue.
        tracer.warning(tid, "log", f"ledger append failed: {e}")


def _build_history_entry(proposal: dict, fallback_metric: float) -> dict:
    """Build a single experiment_history entry from an annotated proposal.

    Shared between the v1.5 single path and the v1.6 parallel path so the
    row schema stays in sync.

    [v1.8 N6] Now includes `tokens` — the total LLM token count used by the
    planner call (set by `node_propose` from the subagent's `usage` dict).
    Operators can sum `tokens` across history entries to estimate LLM cost
    per run. Defaults to 0 when the proposal didn't carry a `tokens` field
    (e.g. failed-proposal placeholders in parallel mode).
    """
    return {
        "iteration": proposal.get("iteration", 0),
        "description": proposal.get("description", ""),
        "metric": proposal.get("metric", fallback_metric),
        "status": proposal.get("status", "discard"),
        "commit": proposal.get("commit", ""),
        "content_hash": proposal.get("content_hash", ""),  # [v1.4 N8] for dedup
        "tokens": proposal.get("tokens", 0),  # [v1.8 N6] total tokens used
    }


def node_log(state: AutoresearchState) -> dict:
    """Append the experiment result to results.tsv and experiment_history.

    Reads `current_experiment` (annotated by `decide` with `status` +
    `commit` + `metric` under the v1.3 P0-1 graph order) and writes a
    ledger row + history entry.

    Returns a partial state dict with:
      experiment_history — appended with the current experiment entry
      experiment_count   — incremented
      current_experiment — cleared (ready for the next proposal)

    [v1.3 P0-1] No longer returns `status` / `error` — `decide` now resets
    them. Returning them here would clobber `decide`'s reset.

    [v1.6] When `parallel_count > 1`, loops through `current_experiments`
    and writes N ledger rows + N history entries. `experiment_count`
    increments by N. Both `current_experiments` (plural) and
    `current_experiment` (singular) are cleared.
    """
    tid = state.get("trace_id", "")
    results_path = state.get("results_path", "results.tsv")
    parallel_count = int(state.get("parallel_count", 1) or 1)
    history = list(state.get("experiment_history", []) or [])

    # ── [v1.6] Parallel path: log all N experiments ────────────────────────
    if parallel_count > 1:
        proposals = state.get("current_experiments", []) or []
        n = len(proposals)

        # [v1.9 C1] Build ALL N rows as a single string and write them in ONE
        # open("a") call (was: N separate calls). Atomic on POSIX for writes
        # < PIPE_BUF=4096, reduces syscall overhead, and prevents interleaving
        # on Windows. (mimo C3, qwen P2-5)
        batch_rows = ""
        # [v1.9 C4] Track new content_hashes to append to seen_hashes.
        seen_hashes = list(state.get("seen_hashes", []) or [])
        seen_set = set(seen_hashes)
        for proposal in proposals:
            iteration = proposal.get("iteration", state.get("experiment_count", 0) + 1)
            commit = proposal.get("commit", "")
            metric = proposal.get("metric", 0.0)
            status = proposal.get("status", "discard")
            description = proposal.get("description", "")
            # [v1.9 A2] Append the content_hash as the 6th column. Use
            # .get("content_hash", "") so failed-proposal placeholders (no
            # hash) write empty — backward compatible with the new 6-col header.
            content_hash = proposal.get("content_hash", "")

            # Sanitize description + content_hash — strip newlines/tabs so
            # the row stays one line.
            safe_desc = " ".join(str(description).split())
            safe_hash = " ".join(str(content_hash).split()) if content_hash else ""
            row = f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\t{safe_hash}\n"
            batch_rows += row

            history.append(_build_history_entry(proposal, 0.0))

            # [v1.9 C4] Append to seen_hashes (deduped, capped at 1000).
            if content_hash and content_hash not in seen_set:
                seen_set.add(content_hash)
                seen_hashes.append(content_hash)

        # [v1.9 C1] Single atomic batched write — was N separate _append_to_ledger calls.
        _append_to_ledger(results_path, batch_rows, tid)

        # [v1.3 P2-3] Cap history to prevent state bloat on long runs.
        if len(history) > 100:
            history = history[-100:]
        # [v1.9 C4] Cap seen_hashes at 1000 (keep most recent — older ones
        # are less likely to re-appear).
        if len(seen_hashes) > 1000:
            seen_hashes = seen_hashes[-1000:]

        new_count = state.get("experiment_count", 0) + n
        # [v1.9 D5] iteration_count increments by 1 per ITERATION (not by N).
        new_iter_count = state.get("iteration_count", 0) + 1
        tracer.step(
            tid, "log",
            f"parallel: logged {n} experiments (total: {new_count}, iter: {new_iter_count})",
        )

        return {
            "experiment_history": history,
            "experiment_count": new_count,
            "iteration_count": new_iter_count,  # [v1.9 D5]
            "seen_hashes": seen_hashes,  # [v1.9 C4]
            "current_experiments": [],  # clear for the next iteration
            "current_experiment": {},   # backward compat
            # [v1.3 P0-1] status/error reset moved to decide.py.
        }

    # ── v1.5 single-experiment path (unchanged) ────────────────────────────
    proposal = state.get("current_experiment", {}) or {}

    iteration = proposal.get("iteration", state.get("experiment_count", 0) + 1)
    commit = proposal.get("commit", "")
    metric = proposal.get("metric", state.get("current_metric", 0.0))
    # [v1.3 P0-1] decide now annotates status BEFORE log runs, so this reads
    # the correct "keep"/"discard" (was: always "discard" because log ran first).
    status = proposal.get("status", "discard")
    description = proposal.get("description", "")
    # [v1.9 A2] Append the content_hash as the 6th column. Use .get(..., "")
    # so failed-proposal placeholders (no hash) write empty.
    content_hash = proposal.get("content_hash", "")

    # 1. Append to results.tsv
    # Sanitize description + content_hash — strip newlines/tabs so the row
    # stays one line.
    safe_desc = " ".join(str(description).split())
    safe_hash = " ".join(str(content_hash).split()) if content_hash else ""
    row = f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\t{safe_hash}\n"
    _append_to_ledger(results_path, row, tid)

    # 2. Append to in-memory experiment_history
    history.append(_build_history_entry(proposal, state.get("current_metric", 0.0)))
    # [v1.3 P2-3] Cap history to prevent state bloat on long runs.
    # Most-recent entries are kept (the LLM only reads the last 20 anyway).
    if len(history) > 100:
        history = history[-100:]

    # [v1.9 C4] Append content_hash to seen_hashes (deduped, capped at 1000).
    seen_hashes = list(state.get("seen_hashes", []) or [])
    if content_hash and content_hash not in seen_hashes:
        seen_hashes.append(content_hash)
        if len(seen_hashes) > 1000:
            seen_hashes = seen_hashes[-1000:]

    new_count = state.get("experiment_count", 0) + 1
    # [v1.9 D5] iteration_count increments by 1 per ITERATION.
    new_iter_count = state.get("iteration_count", 0) + 1
    tracer.step(
        tid, "log",
        f"iter {iteration} logged: {status} {state.get('metric_name', '')}={metric} "
        f"(total experiments: {new_count})",
    )

    return {
        "experiment_history": history,
        "experiment_count": new_count,
        "iteration_count": new_iter_count,  # [v1.9 D5]
        "seen_hashes": seen_hashes,  # [v1.9 C4]
        "current_experiment": {},  # clear for the next proposal
        # [v1.3 P0-1] status/error reset moved to decide.py (which runs first
        # in the new evaluate → decide → log order).
    }
