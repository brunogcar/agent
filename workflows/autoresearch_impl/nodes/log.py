"""Node: log — Append the experiment result to results.tsv and history.

[v1.0] Appends a single tab-separated row to the results ledger and pushes
a corresponding entry into `experiment_history` so the propose node can see
the full context on the next iteration.

Row format (matches the header written by setup.py):
    iteration\tcommit\tmetric\tstatus\tdescription

The ledger is the human-readable audit trail — operators can `tail -f
results.tsv` while the loop runs to watch progress. The in-memory
`experiment_history` is what the LLM sees when proposing the next change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


def _append_to_ledger(results_path: str, row: str) -> None:
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
        tracer.warning("autoresearch", "log", f"ledger append failed: {e}")


def node_log(state: AutoresearchState) -> dict:
    """Append the experiment result to results.tsv and experiment_history.

    Returns a partial state dict with:
      experiment_history — appended with the current experiment entry
      experiment_count   — incremented
      current_experiment — cleared (ready for the next proposal)
    """
    tid = state.get("trace_id", "")
    results_path = state.get("results_path", "results.tsv")
    proposal = state.get("current_experiment", {}) or {}

    iteration = proposal.get("iteration", state.get("experiment_count", 0) + 1)
    commit = proposal.get("commit", "")
    metric = proposal.get("metric", state.get("current_metric", 0.0))
    status = proposal.get("status", "discard")
    description = proposal.get("description", "")

    # 1. Append to results.tsv
    # Sanitize description — strip newlines/tabs so the row stays one line.
    safe_desc = " ".join(str(description).split())
    row = f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\n"
    _append_to_ledger(results_path, row)

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
        "status": "running",
        "error": "",
    }
