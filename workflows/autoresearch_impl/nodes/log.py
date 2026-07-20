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
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


def _append_to_ledger(results_path: str, row: str, tid: str = "") -> None:
    """Append a single row to results.tsv.

    Uses a simple open(..., "a") — autoresearch runs single-threaded per
    branch, so concurrent writers aren't a concern. The row is expected to
    already be tab-separated and end with a newline.
    """
    try:
        p = Path(results_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(row)
    except Exception as e:
        # Non-fatal — the in-memory history is the source of truth for the
        # LLM; the ledger is for human audit. Log and continue.
        tracer.warning(tid, "log", f"ledger append failed: {e}")


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
    """
    tid = state.get("trace_id", "")
    results_path = state.get("results_path", "results.tsv")
    proposal = state.get("current_experiment", {}) or {}

    iteration = proposal.get("iteration", state.get("experiment_count", 0) + 1)
    commit = proposal.get("commit", "")
    metric = proposal.get("metric", state.get("current_metric", 0.0))
    # [v1.3 P0-1] decide now annotates status BEFORE log runs, so this reads
    # the correct "keep"/"discard" (was: always "discard" because log ran first).
    status = proposal.get("status", "discard")
    description = proposal.get("description", "")

    # 1. Append to results.tsv
    # Sanitize description — strip newlines/tabs so the row stays one line.
    safe_desc = " ".join(str(description).split())
    row = f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\n"
    _append_to_ledger(results_path, row, tid)

    # 2. Append to in-memory experiment_history
    history_entry = {
        "iteration": iteration,
        "description": description,
        "metric": metric,
        "status": status,
        "commit": commit,
    }
    history = list(state.get("experiment_history", []) or [])
    history.append(history_entry)
    # [v1.3 P2-3] Cap history to prevent state bloat on long runs.
    # Most-recent entries are kept (the LLM only reads the last 20 anyway).
    if len(history) > 100:
        history = history[-100:]

    new_count = state.get("experiment_count", 0) + 1
    tracer.step(
        tid, "log",
        f"iter {iteration} logged: {status} {state.get('metric_name', '')}={metric} "
        f"(total experiments: {new_count})",
    )

    return {
        "experiment_history": history,
        "experiment_count": new_count,
        "current_experiment": {},  # clear for the next proposal
        # [v1.3 P0-1] status/error reset moved to decide.py (which runs first
        # in the new evaluate → decide → log order).
    }
